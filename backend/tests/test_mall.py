def test_search_cart_checkout_and_cancel(client):
    from test_bc_link import login

    alice = login(client, "alice")
    stationery = client.get("/api/v1/c/shops/nanzhi/products", params={"category": "文具"}).json()
    assert [item["name"] for item in stationery] == ["棉麻笔记本"]
    banned = next(item for item in client.get("/api/v1/b/products", headers=login(client, "merchant")).json() if item["name"] == "刺绣姓名贴")
    assert client.get(f"/api/v1/c/shops/nanzhi/products/{banned['id']}").status_code == 404

    notebook = stationery[0]
    sku = notebook["skus"][0]
    added = client.post("/api/v1/c/shops/nanzhi/cart", headers=alice, json={"sku_id": sku["id"], "quantity": 1})
    assert added.status_code == 200, added.text
    assert added.json()["freight_yuan"] == 8
    order = client.post(
        "/api/v1/c/shops/nanzhi/cart/checkout",
        headers=alice,
        json={"receiver": "小满", "phone": "13800001111", "address": "长沙市岳麓区示范路 1 号"},
    )
    assert order.status_code == 200, order.text
    assert order.json()["goods_yuan"] == 32
    assert client.get("/api/v1/c/shops/nanzhi/cart", headers=alice).json()["items"] == []

    mug = next(item for item in client.get("/api/v1/c/shops/nanzhi/products").json() if item["name"] == "陶瓷马克杯")
    before = mug["skus"][0]["stock"]
    created = client.post(
        "/api/v1/c/shops/nanzhi/orders",
        headers=alice,
        json={"sku_id": mug["skus"][0]["id"], "quantity": 1, "address": "长沙市岳麓区示范路 1 号"},
    )
    cancelled = client.post(f"/api/v1/c/orders/{created.json()['order_no']}/cancel", headers=alice)
    assert cancelled.json()["status"] == "cancelled"
    again = next(item for item in client.get("/api/v1/c/shops/nanzhi/products").json() if item["name"] == "陶瓷马克杯")
    assert again["skus"][0]["stock"] == before

    addresses = client.get("/api/v1/c/addresses", headers=alice).json()
    assert addresses[0]["receiver"] == "小满"
