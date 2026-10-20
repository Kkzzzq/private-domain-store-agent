from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.tables import Shop, ShopAssistantProfile
from app.services.assistant_identity import initialize_assistant_names


def login(client, username):
    token = client.post("/api/v1/auth/login", json={"username": username, "password": username + "123"}).json()["access_token"]
    return {"Authorization": "Bearer " + token}


def test_ai_name_generated_once_and_stable_after_shop_rename(client):
    class Model:
        calls = 0
        def invoke(self, messages):
            self.calls += 1
            return AIMessage(content="小枝")
    model = Model()
    with SessionLocal() as db:
        shop = db.scalar(select(Shop).where(Shop.share_code == "nanzhi"))
        db.delete(db.get(ShopAssistantProfile, shop.id))
        db.commit()
        assert initialize_assistant_names(db, model) == 1
        assert initialize_assistant_names(db, model) == 0
        assert model.calls == 1
    headers = login(client, "merchant")
    updated = client.patch("/api/v1/b/shop", headers=headers, json={"name": "南枝生活馆"})
    assert updated.json()["assistant_name"] == "小枝"


def test_merchant_can_customize_and_buyer_cannot(client):
    response = client.patch("/api/v1/b/shop", headers=login(client, "merchant"), json={"assistant_name": "小南"})
    assert response.status_code == 200
    assert response.json()["assistant_name"] == "小南"
    public = client.get("/api/v1/c/shops/nanzhi")
    assert public.json()["assistant_name"] == "小南"
    assert client.patch("/api/v1/b/shop", headers=login(client, "alice"), json={"assistant_name": "越权"}).status_code == 403


def test_invalid_name_is_rejected(client):
    headers = login(client, "merchant")
    for name in ("", "字" * 11, "<script>", "有 空格"):
        assert client.patch("/api/v1/b/shop", headers=headers, json={"assistant_name": name}).status_code == 422


def test_invalid_ai_name_uses_persisted_fallback(client):
    class Model:
        def invoke(self, messages):
            return AIMessage(content="<script>alert(1)</script>")
    with SessionLocal() as db:
        shop = db.scalar(select(Shop).where(Shop.share_code == "nanzhi"))
        db.delete(db.get(ShopAssistantProfile, shop.id))
        db.commit()
        initialize_assistant_names(db, Model())
        profile = db.get(ShopAssistantProfile, shop.id)
        assert profile.source == "fallback" and profile.name == "小枝"
        assert initialize_assistant_names(db, Model()) == 0


def test_custom_name_limit_and_automatic_name_upgrade(client):
    headers = login(client, "merchant")
    response = client.patch("/api/v1/b/shop", headers=headers, json={"assistant_name": "一二三四五六七八九十"})
    assert response.status_code == 200
    with SessionLocal() as db:
        shop = db.scalar(select(Shop).where(Shop.share_code == "nanzhi"))
        profile = db.get(ShopAssistantProfile, shop.id)
        initialize_assistant_names(db)
        assert profile.name == "一二三四五六七八九十"
        profile.name, profile.source = "小南枝", "ai"
        db.commit()
        initialize_assistant_names(db)
        assert profile.name == "小枝"
