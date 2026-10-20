import json

import pytest
from sqlalchemy import select

from app.agent.context import Actor, reset_actor, set_actor
from app.agent.product_preview import product_preview
from app.db.session import SessionLocal
from app.models.tables import Product, Shop, Sku, User


@pytest.fixture()
def preview_actor(client):
    events = []
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        shop = db.scalar(select(Shop).where(Shop.share_code == "nanzhi"))
        token = set_actor(db, Actor(user.id, user.role, user.username, shop.id, progress=events.append))
        try:
            yield db, shop, events
        finally:
            reset_actor(token)


def test_preview_reads_fresh_inventory(preview_actor):
    db, shop, events = preview_actor
    product_preview("抱枕有货吗")
    assert events and events[0]["type"] == "preview"
    product = db.scalar(select(Product).where(Product.shop_id == shop.id, Product.name == "亚麻抱枕套"))
    product.skus[0].stock = 3
    db.commit()
    product_preview("抱枕有货吗")
    assert "库存3" in events[-1]["answer"]
    assert events[-1]["answer"] != events[0]["answer"]


@pytest.mark.parametrize("message", ["这个还有货吗", "抱枕和杯多少钱", "推荐100元内的杯子", "抱枕有货吗，能退吗", "修改抱枕价格", "我的订单多少钱", "便宜的杯子价格"])
def test_complex_or_contextual_messages_do_not_guess(preview_actor, message):
    product_preview(message)
    assert preview_actor[2] == []


def test_unknown_sku_does_not_preview(preview_actor):
    product_preview("SKU999999有货吗")
    assert preview_actor[2] == []


def test_other_shop_sku_is_not_exposed(preview_actor):
    db, _, events = preview_actor
    owner = User(username="preview_other", password_hash="unused", role="merchant")
    db.add(owner)
    db.flush()
    shop = Shop(merchant_id=owner.id, name="另一个店", share_code="preview-other")
    db.add(shop)
    db.flush()
    product = Product(shop_id=shop.id, name="不可跨店查看的杯", status="on", skus=[Sku(spec="私有规格", price_cents=100, stock=99)])
    db.add(product)
    db.commit()
    product_preview(f"SKU{product.skus[0].id}有货吗")
    assert events == []


def test_explicit_product_query_returns_one_final_result_without_model(client, monkeypatch):
    def forbidden_model(*args, **kwargs):
        raise AssertionError("Explicit product facts must not wait for the model")
    monkeypatch.setattr("app.agent.assistant.create_chat_model", forbidden_model)
    monkeypatch.setattr("app.agent.assistant.run_tool_loop", forbidden_model)
    token = client.post("/api/v1/auth/login", json={"username": "alice", "password": "alice123"}).json()["access_token"]
    response = client.post("/api/v1/c/shops/nanzhi/chat/stream", headers={"Authorization": "Bearer " + token}, json={"message": "抱枕有货吗"})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert not any(event["type"] == "preview" for event in events)
    assert events[-1]["type"] == "result"
    assert events[-1]["data"]["mode"] == "direct"
