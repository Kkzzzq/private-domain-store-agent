"""浏览记录是跨店铺的，下架商品保留但带标注。"""

import time

from test_bc_link import find, login


def _open_second_shop(client) -> dict:
    """再开一家店，用来验证浏览记录不分店铺。"""
    reg = client.post(
        "/api/v1/auth/register",
        json={"username": "othershop", "password": "other123", "role": "merchant", "nickname": "别家"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    shop = client.get("/api/v1/b/shop", headers=headers).json()
    product = client.post(
        "/api/v1/b/products",
        headers=headers,
        json={"name": "别家茶杯", "category": "餐具", "skus": [{"spec": "单只", "price_yuan": 88, "stock": 5}]},
    ).json()
    client.post(f"/api/v1/b/products/{product['id']}/status", headers=headers, json={"action": "on"})
    return {"headers": headers, "shop": shop, "product": product}


def test_history_spans_shops_and_keeps_order(client):
    alice = login(client, "alice")
    other = _open_second_shop(client)
    products = client.get("/api/v1/c/shops/nanzhi/products").json()
    pillow = find(products, "亚麻抱枕套")
    mug = find(products, "陶瓷马克杯")

    client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}", headers=alice)
    client.get(f"/api/v1/c/shops/nanzhi/products/{mug['id']}", headers=alice)
    client.get(f"/api/v1/c/shops/{other['shop']['share_code']}/products/{other['product']['id']}", headers=alice)

    rows = client.get("/api/v1/c/history", headers=alice).json()
    assert [item["name"] for item in rows] == ["别家茶杯", "陶瓷马克杯", "亚麻抱枕套"]
    assert {item["shop_name"] for item in rows} == {"南枝手作", "别家"}

    # 再看一次抱枕，它应该回到最前面，而且不重复
    client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}", headers=alice)
    rows = client.get("/api/v1/c/history", headers=alice).json()
    assert [item["name"] for item in rows] == ["亚麻抱枕套", "别家茶杯", "陶瓷马克杯"]


def test_history_is_per_user(client):
    alice = login(client, "alice")
    bob = login(client, "bob")
    pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")

    client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}", headers=alice)
    assert [item["name"] for item in client.get("/api/v1/c/history", headers=alice).json()] == ["亚麻抱枕套"]
    assert client.get("/api/v1/c/history", headers=bob).json() == []

    client.delete("/api/v1/c/history", headers=alice)
    assert client.get("/api/v1/c/history", headers=alice).json() == []


def test_anonymous_visits_are_not_recorded(client):
    alice = login(client, "alice")
    pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")

    # 没带 token 的浏览不该算进任何人的记录
    client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}")
    assert client.get("/api/v1/c/history", headers=alice).json() == []


def test_history_drops_entries_older_than_seven_days(client):
    from app.db.redis_client import get_redis

    alice = login(client, "alice")
    pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    mug = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "陶瓷马克杯")
    client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}", headers=alice)
    client.get(f"/api/v1/c/shops/nanzhi/products/{mug['id']}", headers=alice)

    # 手动把抱枕的时间改成 8 天前，它应该不再出现在列表里
    me = client.get("/api/v1/auth/me", headers=alice).json()
    redis = get_redis()
    key = f"history:{me['id']}"
    rows = redis.get_json(key) or []
    stale = int(time.time()) - 8 * 24 * 3600
    rows = [{**row, "at": stale} if row["id"] == pillow["id"] else row for row in rows]
    redis.set_json(key, rows, ex=7 * 24 * 3600)

    names = [item["name"] for item in client.get("/api/v1/c/history", headers=alice).json()]
    assert names == ["陶瓷马克杯"]


def test_off_shelf_items_stay_in_history_with_label(client):
    alice = login(client, "alice")
    merchant = login(client, "merchant")
    products = client.get("/api/v1/c/shops/nanzhi/products").json()
    pillow = find(products, "亚麻抱枕套")
    mug = find(products, "陶瓷马克杯")

    # 先在售的时候看一眼，记录才进得去
    client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}", headers=alice)
    client.get(f"/api/v1/c/shops/nanzhi/products/{mug['id']}", headers=alice)

    # 下架抱枕，禁售马克杯
    assert client.post(f"/api/v1/b/products/{pillow['id']}/status", headers=merchant, json={"action": "off"}).status_code == 200
    # 禁售由平台设置，商家接口没有禁售权限。
    assert client.post(f"/api/v1/b/products/{mug['id']}/status", headers=merchant, json={"action": "ban"}).status_code == 403
    from app.db.session import SessionLocal
    from app.models.tables import Product
    from app.services.catalog import invalidate_catalog_cache
    with SessionLocal() as db:
        db.get(Product, mug['id']).status = "banned"
        db.commit()
    invalidate_catalog_cache()

    # 首页和详情页不再出现
    listed = {item["name"] for item in client.get("/api/v1/c/shops/nanzhi/products").json()}
    assert "亚麻抱枕套" not in listed and "陶瓷马克杯" not in listed
    assert client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}").status_code == 404
    assert client.get(f"/api/v1/c/shops/nanzhi/products/{mug['id']}").status_code == 404

    # 浏览记录保留，并带上标注
    rows = client.get("/api/v1/c/history", headers=alice).json()
    by_name = {item["name"]: item for item in rows}
    assert set(by_name) == {"亚麻抱枕套", "陶瓷马克杯"}
    assert by_name["亚麻抱枕套"]["shelf_label"] == "已下架"
    assert by_name["陶瓷马克杯"]["shelf_label"] == "已禁售"
    assert by_name["亚麻抱枕套"]["available"] is False
    assert by_name["陶瓷马克杯"]["available"] is False
    # 价格还在，只是不能直接买
    assert by_name["亚麻抱枕套"]["price_from"] == 59
    assert all(not sku["purchasable"] for sku in by_name["亚麻抱枕套"]["skus"])


def test_closed_shop_marks_items_as_unavailable(client):
    alice = login(client, "alice")
    merchant = login(client, "merchant")
    pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}", headers=alice)
    client.patch("/api/v1/b/shop", headers=merchant, json={"status": "closed"})

    rows = client.get("/api/v1/c/history", headers=alice).json()
    assert rows[0]["shelf_label"] == "店铺停业"
    assert rows[0]["available"] is False
