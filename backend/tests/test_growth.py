from datetime import timedelta

from test_bc_link import find, login, sku_of


def test_notebook_has_purchase_limit(client):
    alice = login(client, "alice")
    notebook = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "棉麻笔记本")
    assert notebook["limit_per_user"] == 2
    sku = notebook["skus"][0]
    first = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": sku["id"], "quantity": 2, "address": "长沙市岳麓区示范路 1 号"},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": sku["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"},
    )
    assert second.status_code == 400
    assert "限购 2 件" in second.json()["detail"]


def test_cannot_oversell_when_stock_is_short(client):
    alice = login(client, "alice")
    bob = login(client, "bob")
    candle = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "大豆香薰蜡烛")
    sku = candle["skus"][0]
    assert sku["stock"] == 0
    blocked = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": sku["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"},
    )
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == "库存不足"

    mug = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "陶瓷马克杯")
    mug_sku = sku_of(mug, "单只")
    too_many = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=bob,
        json={"sku_id": mug_sku["id"], "quantity": 20, "address": "益阳市赫山区示范街 8 号"},
    )
    assert too_many.status_code == 400
    assert too_many.json()["detail"] == "库存不足"


def test_pending_order_times_out_and_returns_stock(client):
    from app.db.session import SessionLocal
    from app.models.tables import utcnow
    from app.services.orders import auto_cancel_expired

    alice = login(client, "alice")
    mug = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "陶瓷马克杯")
    sku = sku_of(mug, "单只")
    before = sku["stock"]
    created = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": sku["id"], "quantity": 3, "address": "长沙市岳麓区示范路 1 号"},
    ).json()
    assert created["expires_in_seconds"] > 0
    assert sku_of(find(client.get("/api/v1/c/shops/nanzhi/products").json(), "陶瓷马克杯"), "单只")["stock"] == before - 3

    db = SessionLocal()
    try:
        assert auto_cancel_expired(db, utcnow() - timedelta(minutes=1)) == 0
        assert auto_cancel_expired(db, utcnow() + timedelta(minutes=40)) == 1
    finally:
        db.close()

    orders = client.get("/api/v1/c/orders", headers=alice, params={"share_code": "nanzhi"}).json()
    target = next(item for item in orders if item["order_no"] == created["order_no"])
    assert target["status"] == "cancelled"
    assert sku_of(find(client.get("/api/v1/c/shops/nanzhi/products").json(), "陶瓷马克杯"), "单只")["stock"] == before


def test_batch_ship_reports_what_it_skipped(client):
    b_headers = login(client, "merchant")
    alice = login(client, "alice")
    mug = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "陶瓷马克杯")
    sku = sku_of(mug, "单只")
    first = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": sku["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"},
    ).json()
    client.post(f"/api/v1/c/orders/{first['order_no']}/pay", headers=alice)
    # 这个还是待支付，批量发货里应该被跳过
    second = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": sku["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"},
    ).json()

    result = client.post(
        "/api/v1/b/orders/ship-batch",
        headers=b_headers,
        json={"order_nos": [first["order_no"], second["order_no"], "PS000000000000"]},
    ).json()
    assert result["shipped"] == [first["order_no"]]
    assert {item["order_no"] for item in result["skipped"]} == {second["order_no"], "PS000000000000"}
    assert any("待支付" in item["reason"] for item in result["skipped"] if item["order_no"] == second["order_no"])


def test_favorite_and_browsing_history_are_per_user(client):
    alice = login(client, "alice")
    bob = login(client, "bob")
    pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}", headers=alice)

    turned_on = client.post(f"/api/v1/c/shops/nanzhi/favorites/{pillow['id']}", headers=alice)
    assert turned_on.json()["favorited"] is True
    mine = client.get("/api/v1/c/shops/nanzhi/favorites", headers=alice).json()
    assert [item["name"] for item in mine] == ["亚麻抱枕套"]
    assert mine[0]["favorited"] is True
    assert client.get("/api/v1/c/shops/nanzhi/favorites", headers=bob).json() == []

    detail = client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}", headers=alice).json()
    assert detail["favorited"] is True
    assert client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}").json()["favorited"] is False

    history = client.get("/api/v1/c/shops/nanzhi/history", headers=alice).json()
    assert [item["name"] for item in history] == ["亚麻抱枕套"]
    client.delete("/api/v1/c/shops/nanzhi/history", headers=alice)
    assert client.get("/api/v1/c/shops/nanzhi/history", headers=alice).json() == []

    off = client.post(f"/api/v1/c/shops/nanzhi/favorites/{pillow['id']}", headers=alice)
    assert off.json()["favorited"] is False
    assert client.get("/api/v1/c/shops/nanzhi/favorites", headers=alice).json() == []


def test_review_only_after_completed_order(client):
    alice = login(client, "alice")
    bob = login(client, "bob")
    plate = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "手作餐盘")
    assert plate["rating_avg"] == 5.0
    assert plate["review_count"] == 1
    reviews = client.get(f"/api/v1/c/shops/nanzhi/products/{plate['id']}/reviews").json()
    assert "釉面很好看" in reviews[0]["content"]
    assert reviews[0]["nickname"] == "小*"

    pending = client.get("/api/v1/c/reviews/pending", headers=alice).json()
    assert pending == []

    mug = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "陶瓷马克杯")
    sku = sku_of(mug, "单只")
    order = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": sku["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"},
    ).json()
    items = client.get("/api/v1/c/orders", headers=alice, params={"share_code": "nanzhi"}).json()
    target = next(item for item in items if item["order_no"] == order["order_no"])
    item_index = target["items"][0]
    not_yet = client.post(
        "/api/v1/c/reviews",
        headers=alice,
        json={"order_item_id": 9999, "rating": 5, "content": "还行"},
    )
    assert not_yet.status_code == 400

    client.post(f"/api/v1/c/orders/{order['order_no']}/pay", headers=alice)
    client.post(f"/api/v1/b/orders/{order['order_no']}/ship", headers=login(client, "merchant"))
    client.post(f"/api/v1/c/orders/{order['order_no']}/confirm", headers=alice)
    still_pending = client.get("/api/v1/c/reviews/pending", headers=alice).json()
    assert len(still_pending) == 1
    assert still_pending[0]["product_id"] == item_index["product_id"]

    created = client.post(
        "/api/v1/c/reviews",
        headers=alice,
        json={"order_item_id": still_pending[0]["order_item_id"], "rating": 4, "content": "杯子手感不错"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["rating"] == 4
    assert client.get("/api/v1/c/reviews/pending", headers=alice).json() == []
    again = client.post(
        "/api/v1/c/reviews",
        headers=alice,
        json={"order_item_id": still_pending[0]["order_item_id"], "rating": 1, "content": "重复"},
    )
    assert again.status_code == 409
    assert client.get("/api/v1/c/reviews/pending", headers=bob).json() == []
    updated = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "陶瓷马克杯")
    assert updated["rating_avg"] == 4.0
    assert updated["review_count"] == 1


def test_sku_exposes_market_price_for_discount(client):
    product = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    white = sku_of(product, "米白")
    assert white["price_yuan"] == 59
    assert white["market_price_yuan"] == 89
    b_headers = login(client, "merchant")
    b_product = find(client.get("/api/v1/b/products", headers=b_headers).json(), "亚麻抱枕套")
    assert sku_of(b_product, "米白")["market_price_yuan"] == 89
    # 商家改价时可以一起改划线价
    updated = client.patch(
        f"/api/v1/b/skus/{white['id']}",
        headers=b_headers,
        json={"market_price_yuan": 99},
    )
    assert updated.status_code == 200
    assert sku_of(updated.json(), "米白")["market_price_yuan"] == 99
    assert sku_of(find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套"), "米白")[
        "market_price_yuan"
    ] == 99


def test_shop_theme_is_saved_and_validated(client):
    b_headers = login(client, "merchant")
    saved = client.patch(
        "/api/v1/b/shop",
        headers=b_headers,
        json={"logo_url": "/covers/shop.svg", "theme_color": "#1d3d33"},
    )
    assert saved.status_code == 200
    assert saved.json()["theme_color"] == "#1d3d33"
    assert client.get("/api/v1/c/shops/nanzhi").json()["theme_color"] == "#1d3d33"
    bad = client.patch("/api/v1/b/shop", headers=b_headers, json={"theme_color": "green"})
    assert bad.status_code == 422
