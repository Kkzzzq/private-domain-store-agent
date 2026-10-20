import json

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.agent.context import Actor, current, reset_actor, set_actor
from app.agent.guard import execute_tool
from app.agent.intent import classify
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tables import Product, Shop, Sku, User


@pytest.fixture()
def catalog_actor(client):
    with SessionLocal() as db:
        buyer = db.scalar(select(User).where(User.username == "alice"))
        shop = db.scalar(select(Shop).where(Shop.share_code == "nanzhi"))
        db.add_all([
            Product(shop_id=shop.id, name="测试陶瓷杯", category="测试杯具", description="陶瓷材质，蓝色和白色可选。", status="on",
                    skus=[Sku(spec="低价缺货", price_cents=1000, stock=0), Sku(spec="蓝色", price_cents=4500, stock=6),
                          Sku(spec="白色", price_cents=5500, stock=8), Sku(spec="已下架", price_cents=500, stock=9, status="off")]),
            Product(shop_id=shop.id, name="测试香薰杯", category="测试杯具", description="香薰玻璃杯。", status="on",
                    skus=[Sku(spec="标准", price_cents=2000, stock=20)]),
            Product(shop_id=shop.id, name="测试限购杯", category="测试杯具", description="陶瓷", status="on", limit_per_user=1,
                    skus=[Sku(spec="单只", price_cents=3000, stock=20)]),
            Product(shop_id=shop.id, name="测试下架杯", category="测试杯具", status="off", skus=[Sku(spec="标准", price_cents=100, stock=20)]),
        ])
        db.commit()
        token = set_actor(db, Actor(buyer.id, buyer.role, buyer.username, shop.id))
        try:
            yield db, current()[1]
        finally:
            reset_actor(token)


def test_catalog_is_paged_and_does_not_create_recommendation_cards(catalog_actor):
    db, actor = catalog_actor
    data = json.loads(execute_tool("get_store_catalog", {"limit": 1}))
    assert actor.catalog_loaded and not actor.products
    assert len(data["products"]) == 1 and data["next_offset"] == 1
    assert all(sku["stock"] > 0 for row in data["products"] for sku in row["skus"])
    assert "测试下架杯" not in execute_tool("get_store_catalog", {"limit": 20})


def test_catalog_page_budget_and_offset_do_not_skip_products(catalog_actor):
    db, actor = catalog_actor
    for index in range(21):
        db.add(Product(shop_id=actor.shop_id, name=f"长说明商品{index}", category="测试分页", description="长说明" * 200, status="on",
                       skus=[Sku(spec=f"规格{variant}" + "详情" * 20, price_cents=1000, stock=10) for variant in range(6)]))
    db.commit()
    seen = set()
    offset = 0
    for _ in range(100):
        data = json.loads(execute_tool("get_store_catalog", {"offset": offset, "limit": 20}))
        rows = data["products"]
        assert len(json.dumps(rows, ensure_ascii=False)) <= 5000
        assert not seen.intersection(row["id"] for row in rows)
        seen.update(row["id"] for row in rows)
        assert all(len(row["skus"]) <= 4 for row in rows)
        if data["next_offset"] is None:
            break
        offset = data["next_offset"]
    assert len(seen) == data["total_purchasable_products"]


@pytest.mark.parametrize("role", ["customer", "merchant"])
def test_requirements_filter_real_sku_stock_and_quantity_budget(catalog_actor, role):
    db, actor = catalog_actor
    actor.role = role
    execute_tool("get_store_catalog", {})
    result = execute_tool("recommend_products", {"reason": "budget", "budget_yuan": 100, "quantity": 2,
                          "category": "测试杯具", "keywords": ["陶瓷"], "excluded_keywords": ["香薰"], "requirements": "预算100元买两只陶瓷杯"})
    assert [row["name"] for row in actor.products] == ["测试陶瓷杯"]
    assert [sku["spec"] for sku in actor.products[0]["skus"]] == ["蓝色"]
    assert actor.products[0]["price_from"] == 45 and "2件小计¥90.00" in result
    assert "不含运费" in result


def test_no_budget_match_does_not_use_out_of_stock_low_price(catalog_actor):
    db, actor = catalog_actor
    execute_tool("get_store_catalog", {})
    result = execute_tool("recommend_products", {"reason": "budget", "budget_yuan": 15, "keywords": ["测试陶瓷杯"]})
    assert "没有找到" in result and not actor.products


def test_requirements_use_same_sku_and_reject_identity_override(catalog_actor):
    db, actor = catalog_actor
    assert "先调用" in execute_tool("recommend_products", {})
    assert "身份" in execute_tool("get_store_catalog", {"shop_id": 999})
    execute_tool("get_store_catalog", {})
    result = execute_tool("recommend_products", {"keywords": ["测试陶瓷杯", "蓝色", "白色"]})
    assert "没有找到" in result and not actor.products
    assert "参数" in execute_tool("recommend_products", {"quantity": 0})
    assert "参数" in execute_tool("recommend_products", {"keywords": ["   "]})


def test_closed_shop_and_foreign_shop_are_not_recommended(catalog_actor):
    db, actor = catalog_actor
    original_shop = actor.shop_id
    actor.shop_id = 999999
    assert json.loads(execute_tool("get_store_catalog", {}))["total_purchasable_products"] == 0
    assert "没有找到" in execute_tool("recommend_products", {})
    actor.shop_id = original_shop
    db.get(Shop, original_shop).status = "closed"
    db.commit()
    assert json.loads(execute_tool("get_store_catalog", {}))["products"] == []
    assert "没有找到" in execute_tool("recommend_products", {})


def test_recommendation_rechecks_inventory_after_overview(catalog_actor):
    db, actor = catalog_actor
    execute_tool("get_store_catalog", {})
    product = db.scalar(select(Product).where(Product.name == "测试陶瓷杯"))
    for sku in product.skus:
        sku.stock = 0
    db.commit()
    assert "没有找到" in execute_tool("recommend_products", {"keywords": ["测试陶瓷杯"]})
    assert not actor.products


def test_color_constraints_are_applied_to_individual_skus(catalog_actor):
    db, actor = catalog_actor
    execute_tool("get_store_catalog", {})
    execute_tool("recommend_products", {"keywords": ["测试陶瓷杯"], "excluded_keywords": ["蓝色"]})
    assert [sku["spec"] for sku in actor.products[0]["skus"]] == ["白色"]


def test_later_filter_replaces_earlier_candidate_cards(catalog_actor):
    db, actor = catalog_actor
    execute_tool("get_store_catalog", {})
    execute_tool("recommend_products", {"keywords": ["测试陶瓷杯"]})
    assert actor.products
    execute_tool("recommend_products", {"keywords": ["不存在的材质"]})
    assert not actor.products


def test_rule_fallback_does_not_ignore_complex_requirements(catalog_actor):
    from app.agent.fallback import fallback_reply
    answer, traces = fallback_reply("推荐两只陶瓷杯，不要香薰")
    assert "规则兜底" in answer and "不会忽略" in answer
    assert not traces and not current()[1].products


def test_tool_loop_stages_and_followup_history(catalog_actor, monkeypatch):
    from app.agent.assistant import assistant
    monkeypatch.setattr(settings, "agent_mode", "auto")
    monkeypatch.setattr(settings, "agent_require_llm", True)
    class Model:
        def __init__(self):
            self.phase = 0
        def bind_tools(self, tools):
            self.names = [tool.name for tool in tools]
            return self
        def invoke(self, messages):
            self.phase += 1
            if self.phase == 1:
                assert self.names == ["get_store_catalog"]
                return AIMessage(content="", tool_calls=[{"name": "get_store_catalog", "args": {}, "id": "catalog"}])
            if self.phase == 2:
                assert "recommend_products" in self.names and "测试陶瓷杯" in messages[-1].content
                return AIMessage(content="", tool_calls=[{"name": "recommend_products", "args": {"keywords": ["测试陶瓷杯"], "quantity": 2, "budget_yuan": 100}, "id": "recommend"}])
            return AIMessage(content="需求：两只100元以内陶瓷杯。推荐蓝色单只45元，两只90元，不含运费。")
    db, actor = catalog_actor
    result = assistant.chat(user_id=actor.user_id, shop_id=actor.shop_id, session_id=None, message="帮我选两只陶瓷杯，100元以内", llm=Model())
    assert result["mode"] == "llm"
    assert [trace["tool"] for trace in result["tools"]] == ["get_store_catalog", "recommend_products"]
    assert result["products"][0]["name"] == "测试陶瓷杯"
    actor.products.clear()
    session = assistant.sessions.load(actor.user_id, actor.shop_id, result["session_id"])
    assert "100元" in session["messages"][0]["content"]


@pytest.mark.parametrize("message", ["帮我选个适合送朋友的", "推荐可以退货的杯子", "便宜一点", "换一个不要这个材质", "想买份礼物", "换白色"])
def test_recommendation_intents(message):
    assert classify(message) == "recommend"


def test_refund_word_is_not_mistaken_for_product_style():
    assert classify("订单杯子破损想换货，怎么联系商家，不要直接办理退款") == "policy"
    assert classify("换一款白色商品") == "recommend"


@pytest.mark.parametrize("skip_initial", [False, True])
def test_overview_only_no_match_answer_is_corrected_into_filter(catalog_actor, monkeypatch, skip_initial):
    from app.agent.assistant import assistant
    monkeypatch.setattr(settings, "agent_mode", "auto")
    monkeypatch.setattr(settings, "agent_require_llm", True)
    class Model:
        def __init__(self):
            self.phase = 0
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            self.phase += 1
            phase = self.phase - int(skip_initial)
            if phase <= 0 or phase == 2:
                return AIMessage(content="预算不足，没有匹配。")
            if phase == 1:
                return AIMessage(content="", tool_calls=[{"name": "get_store_catalog", "args": {}, "id": "catalog"}])
            if phase == 3:
                return AIMessage(content="", tool_calls=[{"name": "recommend_products", "args": {"budget_yuan": 10, "quantity": 2, "keywords": ["测试陶瓷杯"]}, "id": "filter"}])
            return AIMessage(content="筛选后没有满足两件10元预算的陶瓷杯。")
    db, actor = catalog_actor
    result = assistant.chat(user_id=actor.user_id, shop_id=actor.shop_id, session_id=None, message="预算10元推荐两件陶瓷杯", llm=Model())
    assert [trace["tool"] for trace in result["tools"]] == ["get_store_catalog", "recommend_products"]
    assert not result["products"] and result["model_retries"] == 1 + int(skip_initial)


def test_clarification_is_an_explicit_stage_without_cards(catalog_actor, monkeypatch):
    from app.agent.assistant import assistant
    monkeypatch.setattr(settings, "agent_mode", "auto")
    monkeypatch.setattr(settings, "agent_require_llm", True)
    class Model:
        def __init__(self):
            self.phase = 0
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            self.phase += 1
            if self.phase == 1:
                return AIMessage(content="", tool_calls=[{"name": "get_store_catalog", "args": {}, "id": "catalog"}])
            if self.phase == 2:
                return AIMessage(content="", tool_calls=[{"name": "clarify_recommendation", "args": {"fields": ["budget", "preferences"]}, "id": "clarify"}])
            return AIMessage(content="预算多少？喜欢什么材质或颜色？")
    db, actor = catalog_actor
    result = assistant.chat(user_id=actor.user_id, shop_id=actor.shop_id, session_id=None, message="帮我选个礼物", llm=Model())
    assert result["mode"] == "llm" and not result["products"]
    assert result["tools"][-1]["tool"] == "clarify_recommendation"


def test_filter_stage_correction_is_not_unbounded(catalog_actor, monkeypatch):
    from fastapi import HTTPException
    from app.agent.assistant import assistant
    monkeypatch.setattr(settings, "agent_mode", "auto")
    monkeypatch.setattr(settings, "agent_require_llm", True)
    class Model:
        phase = 0
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            self.phase += 1
            if self.phase == 1:
                return AIMessage(content="", tool_calls=[{"name": "get_store_catalog", "args": {}, "id": "catalog"}])
            return AIMessage(content="我直接根据概览回答。")
    model = Model()
    db, actor = catalog_actor
    with pytest.raises(HTTPException):
        assistant.chat(user_id=actor.user_id, shop_id=actor.shop_id, session_id=None, message="推荐商品", llm=model)
    assert model.phase == 3
