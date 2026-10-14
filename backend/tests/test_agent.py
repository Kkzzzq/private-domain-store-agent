import pytest
from sqlalchemy import select

from app.agent.context import Actor, reset_actor, set_actor
from app.agent.guard import execute_tool
from app.agent.intent import classify
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tables import AgentToolLog, User
from app.rag.cleaner import structured_chunks
from app.services.session import compact_messages
from test_bc_link import login


def chat(client, headers, message, session=None, merchant=False):
    return client.post("/api/v1/b/chat" if merchant else "/api/v1/c/shops/nanzhi/chat", headers=headers,
                       json={"message": message, "session_id": session})


def test_both_roles_and_session_isolation(client):
    buyer = login(client, "alice")
    merchant = login(client, "merchant")
    response = chat(client, merchant, "查询订单 PS202601200001", merchant=True)
    assert response.status_code == 200
    assert "PS202601200001" in response.json()["answer"]
    assert "益阳" not in response.json()["answer"]
    assert "没有找到这个订单" in chat(client, buyer, "查询订单 PS202601200001").json()["answer"]
    assert chat(client, buyer, "经营概览", merchant=True).status_code == 403
    assert chat(client, merchant, "我的订单").status_code == 403
    assert "待发货" in chat(client, merchant, "经营概览", merchant=True).json()["answer"]
    assert "库存" in chat(client, merchant, "库存预警", merchant=True).json()["answer"]
    session = response.json()["session_id"]
    assert client.get(f"/api/v1/c/shops/nanzhi/sessions/{session}", headers=buyer).json()["messages"] == []
    assert client.get(f"/api/v1/b/sessions/{session}", headers=merchant).json()["messages"]
    assert chat(client, buyer, "   ").status_code == 422
    with SessionLocal() as db:
        logs = db.scalars(select(AgentToolLog)).all()
        assert any(log.flag == "order_not_found_or_denied" for log in logs)
        assert all("PS202601200001" not in log.args for log in logs)


def test_recommendations_and_visibility(client):
    buyer = login(client, "alice")
    merchant = login(client, "merchant")
    hot = chat(client, buyer, "推荐热销商品").json()
    assert hot["products"]
    assert hot["intent"] == "recommend"
    budget = chat(client, buyer, "预算 40 元推荐商品").json()["products"]
    assert budget and all(product["price_from"] <= 40 for product in budget)
    product = hot["products"][0]
    client.get(f"/api/v1/c/shops/nanzhi/products/{product['id']}", headers=buyer)
    assert chat(client, buyer, "根据浏览再推荐几个").status_code == 200
    assert chat(client, buyer, f"推荐商品 {product['id']} 的相似款").status_code == 200
    client.post(f"/api/v1/b/products/{product['id']}/status", headers=merchant, json={"action": "off"})
    assert product["id"] not in [row["id"] for row in chat(client, buyer, "推荐热销商品").json()["products"]]
    client.patch("/api/v1/b/shop", headers=merchant, json={"status": "closed"})
    assert chat(client, buyer, "推荐热销商品").json()["products"] == []


def test_other_shop_merchant_cannot_read_orders(client):
    response = client.post("/api/v1/auth/register", json={"username": "foreign", "password": "foreign123", "role": "merchant"})
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    result = chat(client, headers, "订单 PS202601200001", merchant=True)
    assert "没有找到这个订单" in result.json()["answer"]
    assert "益阳" not in result.text
    assert chat(client, headers, "推荐热销商品", merchant=True).json()["products"] == []


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "agent_rate_limit_per_minute", 2)
    buyer = login(client, "alice")
    assert chat(client, buyer, "你好").status_code == 200
    assert chat(client, buyer, "你好").status_code == 200
    assert chat(client, buyer, "你好").status_code == 429


def test_guard_role_parameters_and_retry(client, monkeypatch):
    from app.agent.tools import IMPL
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        token = set_actor(db, Actor(user.id, user.role, user.username, 1, "testsession"))
        try:
            assert "无权" in execute_tool("merchant_overview", {})
            assert "参数" in execute_tool("query_orders", {"user_id": 999})
            assert "参数" in execute_tool("check_inventory", {"sku_id": -1})
            assert "参数" in execute_tool("recommend_products", {"reason": "budget"})
            attempts = []
            def failing(**kwargs):
                attempts.append(kwargs)
                raise RuntimeError("database-password-secret")
            monkeypatch.setitem(IMPL, "query_orders", failing)
            assert execute_tool("query_orders", {}) == "工具执行失败，请稍后重试。"
            assert len(attempts) == 2
        finally:
            reset_actor(token)


def test_tool_loop_and_model_fallback(client, monkeypatch):
    from langchain_core.messages import AIMessage, ToolMessage
    from app.agent.assistant import assistant
    monkeypatch.setattr(settings, "agent_mode", "auto")
    class Model:
        def bind_tools(self, tools):
            self.tools = tools
            return self
        def invoke(self, messages):
            if isinstance(messages[-1], ToolMessage):
                return AIMessage(content="已查询本店商品")
            return AIMessage(content="", tool_calls=[{"name": "search_products", "args": {"keyword": "抱枕"}, "id": "call1"}])
    class Broken(Model):
        def invoke(self, messages):
            raise RuntimeError("offline")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        token = set_actor(db, Actor(user.id, user.role, user.username, 1))
        try:
            result = assistant.chat(user_id=user.id, shop_id=1, session_id=None, message="有没有抱枕", llm=Model())
            assert result["mode"] == "llm" and result["products"]
            assert result["tools"][0]["tool"] == "search_products"
            result = assistant.chat(user_id=user.id, shop_id=1, session_id=None, message="有没有抱枕", llm=Broken())
            assert result["mode"] == "fallback" and result["notices"]
            assert "亚麻抱枕套" in result["answer"]
        finally:
            reset_actor(token)


def test_order_followup(client):
    merchant = login(client, "merchant")
    response = chat(client, merchant, "订单 PS202601200001", merchant=True).json()
    followup = chat(client, merchant, "这个订单发货了吗", response["session_id"], merchant=True).json()
    assert followup["tools"][0]["args"]["order_no"] == "PS202601200001"


def test_structure_and_bounded_context():
    chunks = structured_chunks("# 售后\n\n## 退货\n\n七天退货。\n\n七天退货。\n\n<!--隐藏-->\n\n## 运费\n\n满99包邮。")
    assert chunks[0]["heading_path"] == "售后 > 退货"
    assert sum(chunk["content"].count("七天退货") for chunk in chunks) == 1
    assert "隐藏" not in str(chunks)
    state = {"summary": "", "messages": [{"role": "user", "content": "订单 PS202601200001 " + "咨询" * 300} for _ in range(20)]}
    compacted, notice = compact_messages(state, 800)
    assert "PS202601200001" in compacted["summary"]
    assert len(compacted["summary"]) + sum(len(row["content"]) for row in compacted["messages"]) <= 800
    assert notice


def test_chroma_rebuild_and_source_metadata(tmp_path):
    from app.rag.knowledge import KnowledgeBase
    class Embeddings:
        def embed_documents(self, texts):
            return [[1.0, 0.0, 0.0] for text in texts]
        def embed_query(self, text):
            return [1.0, 0.0, 0.0]
    class Broken(Embeddings):
        def embed_documents(self, texts):
            raise RuntimeError("offline")
    base = KnowledgeBase(tmp_path)
    chunks = [{"id": "policy-1", "content": "七天退货", "source": "policy.md", "heading_path": "售后 > 退货"}]
    assert base.rebuild(chunks, Embeddings()) == 1
    hit = base.semantic_search("退货", Embeddings())[0]
    assert hit["source"] == "policy.md" and hit["heading_path"] == "售后 > 退货"
    with pytest.raises(RuntimeError):
        base.rebuild(chunks, Broken())
    assert base.has_vectors()


@pytest.mark.parametrize("message,intent", [("我的订单", "order"), ("退货规则", "policy"), ("SKU 1 库存", "inventory"), ("推荐商品", "recommend"), ("经营概览", "overview"), ("库存预警", "low_inventory"), ("有没有抱枕", "product_search"), ("今天天气不错", "unclear")])
def test_intent(message, intent):
    assert classify(message) == intent
