def login(client, username, password="ignored"):
    passwords = {"merchant": "merchant123", "alice": "alice123", "bob": "bob123"}
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": passwords.get(username, password)},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def find(items, name):
    return next(item for item in items if item["name"] == name)


def sku_of(product, spec):
    return next(item for item in product["skus"] if item["spec"] == spec)


def test_pages_exist(client):
    assert "商家后台" in client.get("/b.html").text
    assert "买家登录" in client.get("/c.html").text
    assert "分享码" in client.get("/").text


def test_c_only_sees_on_sale_products_from_the_same_shop(client):
    b_headers = login(client, "merchant")
    b_products = client.get("/api/v1/b/products", headers=b_headers).json()
    c_products = client.get("/api/v1/c/shops/nanzhi/products").json()

    assert find(b_products, "桌面收纳盒")["status"] == "off"
    assert [item["name"] for item in c_products][:3] == ["亚麻抱枕套", "陶瓷马克杯", "大豆香薰蜡烛"]
    assert "刺绣姓名贴" not in {item["name"] for item in c_products}
    assert "桌面收纳盒" not in {item["name"] for item in c_products}


def test_b_edit_is_what_c_reads_and_old_orders_keep_snapshot(client):
    b_headers = login(client, "merchant")
    c_headers = login(client, "alice")
    pillow = find(client.get("/api/v1/b/products", headers=b_headers).json(), "亚麻抱枕套")
    white = sku_of(pillow, "米白")

    renamed = client.patch(
        f"/api/v1/b/products/{pillow['id']}",
        headers=b_headers,
        json={"name": "水洗亚麻抱枕套", "description": "商家刚改的说明"},
    )
    assert renamed.status_code == 200
    priced = client.patch(
        f"/api/v1/b/skus/{white['id']}",
        headers=b_headers,
        json={"price_yuan": 69, "stock": 18},
    )
    assert priced.status_code == 200

    c_pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "水洗亚麻抱枕套")
    c_white = sku_of(c_pillow, "米白")
    assert c_pillow["description"] == "商家刚改的说明"
    assert c_white["price_yuan"] == 69
    assert c_white["stock"] == 18

    old_order = next(
        item
        for item in client.get("/api/v1/c/orders", headers=c_headers, params={"share_code": "nanzhi"}).json()
        if item["order_no"] == "PS202601150001"
    )
    assert old_order["items"][0]["product_name"] == "亚麻抱枕套"
    assert old_order["total_yuan"] == 59


def test_shelf_ban_and_shop_close_control_whether_c_can_buy(client):
    b_headers = login(client, "merchant")
    c_headers = login(client, "alice")
    products = client.get("/api/v1/b/products", headers=b_headers).json()
    mug = find(products, "陶瓷马克杯")
    mug_sku = sku_of(mug, "单只")

    banned = client.post(
        f"/api/v1/b/products/{mug['id']}/status",
        headers=b_headers,
        json={"action": "ban"},
    )
    assert banned.status_code == 200
    assert "陶瓷马克杯" not in {item["name"] for item in client.get("/api/v1/c/shops/nanzhi/products").json()}
    direct_on = client.post(
        f"/api/v1/b/products/{mug['id']}/status",
        headers=b_headers,
        json={"action": "on"},
    )
    assert direct_on.status_code == 400
    assert "解禁" in direct_on.json()["detail"]

    client.post(f"/api/v1/b/products/{mug['id']}/status", headers=b_headers, json={"action": "unban"})
    assert "陶瓷马克杯" not in {item["name"] for item in client.get("/api/v1/c/shops/nanzhi/products").json()}
    client.post(f"/api/v1/b/products/{mug['id']}/status", headers=b_headers, json={"action": "on"})
    assert "陶瓷马克杯" in {item["name"] for item in client.get("/api/v1/c/shops/nanzhi/products").json()}

    pillow = find(client.get("/api/v1/b/products", headers=b_headers).json(), "亚麻抱枕套")
    blue = sku_of(pillow, "雾蓝")
    client.post(f"/api/v1/b/skus/{blue['id']}/status", headers=b_headers, json={"action": "off"})
    c_pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    assert [item["spec"] for item in c_pillow["skus"]] == ["米白"]

    hidden = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=c_headers,
        json={"sku_id": blue["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"},
    )
    assert hidden.status_code == 400
    assert hidden.json()["detail"] == "没有找到这个商品"

    client.patch("/api/v1/b/shop", headers=b_headers, json={"status": "closed", "notice": "今天休息"})
    shop = client.get("/api/v1/c/shops/nanzhi").json()
    assert shop["notice"] == "今天休息"
    assert client.get("/api/v1/c/shops/nanzhi/products").json() == []
    closed_order = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=c_headers,
        json={"sku_id": mug_sku["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"},
    )
    assert closed_order.json()["detail"] == "店铺未营业"


def test_c_order_lands_on_b_and_cannot_cross_user_or_shop(client):
    b_headers = login(client, "merchant")
    alice = login(client, "alice")
    bob = login(client, "bob")
    mug = find(client.get("/api/v1/b/products", headers=b_headers).json(), "陶瓷马克杯")
    mug_sku = sku_of(mug, "单只")
    before = mug_sku["stock"]

    created = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": mug_sku["id"], "quantity": 2, "address": "长沙市岳麓区示范路 1 号"},
    )
    assert created.status_code == 200, created.text
    order_no = created.json()["order_no"]
    assert created.json()["goods_yuan"] == 78
    assert created.json()["freight_yuan"] == 8
    assert created.json()["total_yuan"] == 86

    paid = client.post(f"/api/v1/c/orders/{order_no}/pay", headers=alice)
    assert paid.json()["status"] == "paid"
    shipped = client.post(f"/api/v1/b/orders/{order_no}/ship", headers=b_headers)
    assert shipped.status_code == 200
    assert shipped.json()["buyer_nickname"] == "小满"

    alice_orders = client.get("/api/v1/c/orders", headers=alice, params={"share_code": "nanzhi"}).json()
    assert next(item["status"] for item in alice_orders if item["order_no"] == order_no) == "shipped"
    assert "益阳" not in str(alice_orders)

    b_orders = client.get("/api/v1/b/orders", headers=b_headers).json()
    assert any(item["order_no"] == "PS202601200001" and "益阳" in item["address"] for item in b_orders)
    after = sku_of(find(client.get("/api/v1/b/products", headers=b_headers).json(), "陶瓷马克杯"), "单只")
    assert after["stock"] == before - 2

    leaked = client.get("/api/v1/c/orders", headers=bob, params={"share_code": "nanzhi"}).json()
    assert order_no not in {item["order_no"] for item in leaked}
    assert client.post(f"/api/v1/c/orders/{order_no}/pay", headers=bob).status_code == 404
    assert client.post("/api/v1/c/shops/nanzhi/orders", headers=b_headers, json={"sku_id": mug_sku["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"}).status_code == 403
    assert client.get("/api/v1/b/products", headers=alice).status_code == 403

    other = client.post(
        "/api/v1/auth/register",
        json={"username": "other", "password": "other123", "role": "merchant", "nickname": "别家"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    other_shop = client.get("/api/v1/b/shop", headers=other_headers).json()
    created_product = client.post(
        "/api/v1/b/products",
        headers=other_headers,
        json={"name": "别家茶杯", "skus": [{"spec": "单只", "price_yuan": 10, "stock": 3}]},
    )
    client.post(
        f"/api/v1/b/products/{created_product.json()['id']}/status",
        headers=other_headers,
        json={"action": "on"},
    )
    assert client.get("/api/v1/b/products", headers=other_headers).json()[0]["name"] == "别家茶杯"
    assert "别家茶杯" not in {item["name"] for item in client.get("/api/v1/c/shops/nanzhi/products").json()}
    assert "别家茶杯" in {
        item["name"] for item in client.get(f"/api/v1/c/shops/{other_shop['share_code']}/products").json()
    }
    foreign = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": created_product.json()["skus"][0]["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"},
    )
    assert foreign.json()["detail"] == "没有找到这个商品"


def test_agent_uses_the_shop_the_customer_entered(client):
    alice = login(client, "alice")
    found = client.post("/api/v1/c/shops/nanzhi/chat", headers=alice, json={"message": "有没有抱枕"})
    assert found.status_code == 200
    assert "亚麻抱枕套" in found.json()["answer"]

    b_headers = login(client, "merchant")
    pillow = find(client.get("/api/v1/b/products", headers=b_headers).json(), "亚麻抱枕套")
    client.post(f"/api/v1/b/products/{pillow['id']}/status", headers=b_headers, json={"action": "off"})
    hidden = client.post("/api/v1/c/shops/nanzhi/chat", headers=alice, json={"message": "有没有抱枕"})
    assert "没有找到在售商品" in hidden.json()["answer"]

    leaked = client.post(
        "/api/v1/c/shops/nanzhi/chat",
        headers=alice,
        json={"message": "查询订单 PS202601200001"},
    )
    assert "没有找到这个订单" in leaked.json()["answer"]
    assert "益阳" not in leaked.json()["answer"]
