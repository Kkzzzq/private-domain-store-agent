import json

import httpx
import pytest

from app.rag.product_images import ImageEmbedder, image_assets, image_input


def test_images_bind_spu_and_each_sku_without_cross_wiring():
    rows = [{"id": 1, "image_url": "/covers/pillow.jpg", "skus": [
        {"id": 11, "image_url": "/covers/pillow-blue.jpg"}, {"id": 12, "image_url": ""}]}]
    assets = image_assets(rows)
    assert assets[0] == {"product_id": 1, "sku_id": 0, "image_url": "/covers/pillow.jpg", "inherited": False}
    assert assets[1]["sku_id"] == 11 and assets[1]["image_url"].endswith("pillow-blue.jpg") and not assets[1]["inherited"]
    assert assets[2]["sku_id"] == 12 and assets[2]["inherited"] and assets[2]["image_url"].endswith("pillow.jpg")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "/covers/../../.env", "/uploads/../../../.env", "//127.0.0.1/private.jpg", "http://127.0.0.1/a.jpg", "/covers/thing.svg"])
def test_image_input_rejects_private_files_and_unsafe_schemes(url):
    with pytest.raises((ValueError, OSError)):
        image_input(url)


def test_image_input_rejects_private_https_dns(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))])
    with pytest.raises(ValueError, match="私网"):
        image_input("https://private.example/a.jpg")


def test_multimodal_endpoint_sends_actual_image_and_validates_vectors(monkeypatch):
    sent = []
    monkeypatch.setattr("app.rag.product_images.embedding_api_key", lambda: "test-key")
    def post(url, **kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(200, json={"output": {"embeddings": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}})
    monkeypatch.setattr("app.rag.product_images.httpx.post", post)
    embedder = ImageEmbedder("qwen3-vl-embedding", {"/covers/test.png": "data:image/png;base64,actual-bytes"})
    doc = json.dumps({"image_url": "/covers/test.png", "fingerprint": "same-content"})
    vectors = embedder.embed_documents(["sku-11\n" + doc, "sku-12\n" + doc])
    assert len(vectors) == 2 and len(sent) == 1
    assert sent[0]["input"]["contents"][0]["image"].startswith("data:image/png;base64,")
    embedder.embed_query("蓝色花纹")
    assert sent[1]["input"]["contents"] == [{"text": "蓝色花纹"}]


def test_image_quota_is_not_reported_as_success(monkeypatch):
    from app.rag.cloud_embeddings import EmbeddingQuotaError
    monkeypatch.setattr("app.rag.product_images.embedding_api_key", lambda: "test-key")
    monkeypatch.setattr("app.rag.product_images.httpx.post", lambda *args, **kwargs: httpx.Response(403, json={"code": "AllocationQuota.FreeTierOnly"}))
    with pytest.raises(EmbeddingQuotaError):
        ImageEmbedder("qwen3-vl-embedding", {}).embed_query("蓝色")


def test_image_result_card_uses_matched_sku_image_and_live_price(client, monkeypatch):
    from sqlalchemy import select
    from app.agent.context import Actor, reset_actor, set_actor
    from app.db.session import SessionLocal
    from app.models.tables import Product, Sku, User
    from app.services.agent_queries import image_products
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        product = Product(shop_id=1, name="图片对应测试", status="on", image_url="/covers/pillow.jpg", skus=[
            Sku(spec="蓝色", image_url="/covers/pillow-blue.jpg", price_cents=3000, stock=3),
            Sku(spec="白色", image_url="", price_cents=4000, stock=2)])
        db.add(product)
        db.commit()
        sku_id = product.skus[0].id
        monkeypatch.setattr("app.rag.product_images.search_product_images", lambda *args: ({(product.id, sku_id)}, {"status": "ready"}))
        token = set_actor(db, Actor(user.id, "customer", user.username, 1))
        try:
            output = json.loads(image_products("蓝色"))
            row = output["候选商品"][0]
            assert row["image_url"] == "/covers/pillow-blue.jpg"
            assert row["spu_image_url"] == "/covers/pillow.jpg"
            assert row["image_bindings"][0]["sku_id"] == sku_id
            assert row["skus"][0]["price_yuan"] == 30
        finally:
            reset_actor(token)
