"""SPU / SKU / C 端宽表三层：商家与平台读 SPU 表，买家只读宽表。

这组测试守的是数据契约，不是页面效果：
草稿只是一个状态值，没有草稿表；SKU 用 spu_id 指向 SPU；
买家端的每个字段都能在宽表里找到来源，不回查权威表。
"""

from sqlalchemy import inspect, select

from test_bc_link import find, login


def _session():
    from app.db.session import SessionLocal

    return SessionLocal()


def test_spu_number_generator_does_not_collide_in_bulk(client):
    """批量灌数据时编号必须唯一，唯一约束撞上就是 500。"""
    from app.models.tables import generate_spu_id

    numbers = [generate_spu_id() for _ in range(5000)]
    assert len(set(numbers)) == len(numbers)


def test_sku_points_at_spu_and_draft_is_only_a_status(client):
    from app.models.tables import CProductView, Product, Sku
    from app.db.session import engine

    tables = set(inspect(engine).get_table_names())
    assert {"products", "skus", "c_product_views"} <= tables
    # 没有单独的草稿表：草稿就是 products.status 的一个取值
    assert not [name for name in tables if "draft" in name]
    assert "product_id" not in {column["name"] for column in inspect(engine).get_columns("skus")}
    assert "spu_id" in {column["name"] for column in inspect(engine).get_columns("skus")}

    with _session() as db:
        sku = db.scalars(select(Sku)).first()
        assert sku is not None
        spu = db.get(Product, sku.spu_id)
        assert spu is not None and spu.id == sku.spu_id
        assert spu.spu_id.startswith("SP")
        # 宽表按 SPU 一行，主键就是 SPU 主键
        view = db.get(CProductView, sku.spu_id)
        assert view is not None and view.spu_id == sku.spu_id
        assert view.payload["id"] == sku.spu_id


def test_draft_stays_out_of_the_wide_table_until_listed(client):
    from app.models.tables import CProductView

    merchant = login(client, "merchant")
    draft = client.post(
        "/api/v1/b/products",
        headers=merchant,
        json={"name": "宽表草稿验证款", "category": "家居", "skus": [{"spec": "标准", "price_yuan": 66, "stock": 3}]},
    ).json()

    # 商家端直接读 SPU 表，草稿照样能看到
    assert find(client.get("/api/v1/b/products", headers=merchant).json(), "宽表草稿验证款")
    with _session() as db:
        assert db.get(CProductView, draft["id"]) is None

    listed = client.get("/api/v1/c/shops/nanzhi/products").json()
    assert not [row for row in listed if row["name"] == "宽表草稿验证款"]
    assert client.get(f"/api/v1/c/shops/nanzhi/products/{draft['id']}").status_code == 404

    client.post(f"/api/v1/b/products/{draft['id']}/status", headers=merchant, json={"action": "on"})
    with _session() as db:
        view = db.get(CProductView, draft["id"])
        assert view is not None and view.listed is True
    assert find(client.get("/api/v1/c/shops/nanzhi/products").json(), "宽表草稿验证款")


def test_buyer_side_reads_the_wide_table_only(client):
    from app.models.tables import CProductView

    with _session() as db:
        view = db.scalars(select(CProductView).where(CProductView.listed.is_(True))).first()
        assert view is not None
        # 只改宽表、不动 SPU：接口若回查权威表，这里就看不到改后的名字
        view.name = "宽表直读验证"
        view.payload = {**view.payload, "name": "宽表直读验证"}
        db.commit()

    products = client.get("/api/v1/c/shops/nanzhi/products").json()
    assert find(products, "宽表直读验证")


def test_merchant_price_change_is_visible_on_buyer_side(client):
    merchant = login(client, "merchant")
    pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    sku_id = pillow["skus"][0]["id"]

    client.patch(f"/api/v1/b/skus/{sku_id}", headers=merchant, json={"price_yuan": 12.34})
    fresh = client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}").json()
    assert fresh["skus"][0]["price_yuan"] == 12.34
    assert fresh["price_from"] == 12.34


def test_wide_table_self_heals_when_authoritative_rows_change(client):
    """绕过服务层直接改 SKU 表，买家端读到的是改后的价：投影会按指纹自愈。"""
    from app.models.tables import Sku

    pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    sku_id = pillow["skus"][0]["id"]
    with _session() as db:
        db.get(Sku, sku_id).price_cents = 4567
        db.commit()

    fresh = client.get(f"/api/v1/c/shops/nanzhi/products/{pillow['id']}").json()
    assert fresh["skus"][0]["price_yuan"] == 45.67

def test_same_second_sku_edits_and_balanced_stock_changes_invalidate_cache(client):
    from app.models.tables import Sku
    pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    first, second = pillow["skus"][:2]
    with _session() as db:
        a, b = db.get(Sku, first["id"]), db.get(Sku, second["id"])
        stamp = a.updated_at.replace(microsecond=0)
        a.stock += 1
        b.stock -= 1
        a.spec = "完整规格指纹"
        a.image_url = "/uploads/fingerprint.jpg"
        db.flush()
        a.updated_at = b.updated_at = stamp
        db.commit()
    fresh = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    sku = next(row for row in fresh["skus"] if row["id"] == first["id"])
    assert sku["stock"] == first["stock"] + 1
    assert sku["spec"] == "完整规格指纹"
    assert sku["image_url"] == "/uploads/fingerprint.jpg"


def test_cart_and_order_images_use_projection_and_orders_keep_snapshots(client):
    from app.models.tables import CProductView
    buyer = login(client, "alice")
    product = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    sku_id = product["skus"][0]["id"]
    added = client.post("/api/v1/c/shops/nanzhi/cart", headers=buyer, json={"sku_id": sku_id, "quantity": 1})
    assert added.status_code == 200, added.text
    order = client.post("/api/v1/c/shops/nanzhi/orders", headers=buyer,
                        json={"sku_id": sku_id, "quantity": 1, "address": "测试收货地址"})
    assert order.status_code == 200, order.text
    with _session() as db:
        view = db.get(CProductView, product["id"])
        view.payload = {**view.payload, "name": "宽表购物车名称", "image_url": "/uploads/projection-only.jpg",
                        "skus": [{**sku, "image_url": "/uploads/projection-only.jpg"} for sku in view.payload["skus"]]}
        db.commit()
    cart = client.get("/api/v1/c/shops/nanzhi/cart", headers=buyer).json()
    assert cart["items"][0]["product_name"] == "宽表购物车名称"
    assert cart["items"][0]["image_url"] == "/uploads/projection-only.jpg"
    orders = client.get("/api/v1/c/orders", headers=buyer).json()
    saved = next(row for row in orders if row["order_no"] == order.json()["order_no"])
    assert saved["items"][0]["image_url"] == "/uploads/projection-only.jpg"
    assert saved["items"][0]["product_name"] == product["name"]
    assert saved["items"][0]["price_yuan"] == product["skus"][0]["price_yuan"]


def test_stock_projection_is_updated_in_order_transaction(client):
    from app.models.tables import CProductView
    buyer = login(client, "alice")
    product = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    sku = product["skus"][0]
    order = client.post("/api/v1/c/shops/nanzhi/orders", headers=buyer,
                        json={"sku_id": sku["id"], "quantity": 1, "address": "测试收货地址"})
    assert order.status_code == 200, order.text
    def stock():
        with _session() as db:
            view = db.get(CProductView, product["id"])
            return next(row["stock"] for row in view.payload["skus"] if row["id"] == sku["id"])
    assert stock() == sku["stock"] - 1
    cancelled = client.post(f"/api/v1/c/orders/{order.json()['order_no']}/cancel", headers=buyer)
    assert cancelled.status_code == 200, cancelled.text
    assert stock() == sku["stock"]


def test_deleting_spu_removes_projection(client):
    from app.models.tables import CProductView, Product
    with _session() as db:
        product = Product(shop_id=1, name="删除投影测试", status="off")
        db.add(product)
        db.commit()
        from app.services.c_projection import refresh_product
        refresh_product(db, product.id)
        product_id = product.id
        assert db.get(CProductView, product_id) is not None
        db.delete(product)
        db.commit()
        assert db.get(CProductView, product_id) is None


def test_history_keeps_same_sku_price_when_all_skus_are_hidden(client):
    merchant, buyer = login(client, "merchant"), login(client, "alice")
    product = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    client.get(f"/api/v1/c/shops/nanzhi/products/{product['id']}", headers=buyer)
    for index, sku in enumerate(product["skus"]):
        updated = client.patch(f"/api/v1/b/skus/{sku['id']}", headers=merchant,
                               json={"price_yuan": 29 + index * 10, "market_price_yuan": 99 - index * 10})
        assert updated.status_code == 200
        assert client.post(f"/api/v1/b/skus/{sku['id']}/status", headers=merchant,
                           json={"action": "off"}).status_code == 200
    saved = find(client.get("/api/v1/c/history", headers=buyer).json(), product["name"])
    assert (saved["price_from"], saved["market_from"]) == (29, 99)
    assert saved["available"] is False
    assert saved["shelf_label"] == "暂无在售规格"
    assert all(not sku["purchasable"] for sku in saved["skus"])


def test_operations_can_search_business_spu_number_and_internal_id(client):
    from test_operations import operator
    merchant, op = login(client, "merchant"), operator(client)
    product = find(client.get("/api/v1/b/products", headers=merchant).json(), "亚麻抱枕套")
    for query in (product["spu_id"], str(product["id"])):
        response = client.get("/api/v1/op/records/products", headers=op, params={"q": query})
        assert response.status_code == 200, response.text
        assert product["id"] in [row["id"] for row in response.json()["items"]]


def test_operations_long_numeric_product_search_does_not_raise(client):
    from test_operations import operator
    response = client.get("/api/v1/op/records/products", headers=operator(client), params={"q": "9" * 80})
    assert response.status_code == 200
    assert response.json()["items"] == []
