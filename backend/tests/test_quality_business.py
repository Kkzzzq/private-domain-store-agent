from test_bc_link import find, login


def test_cart_quantity_validation_preserves_previous_value(client):
    buyer = login(client, "alice")
    product = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    sku = product["skus"][0]
    path = "/api/v1/c/shops/nanzhi/cart"
    for quantity in [0, -1, 21]:
        assert client.post(path, headers=buyer, json={"sku_id": sku["id"], "quantity": quantity}).status_code == 422
    assert client.get(path, headers=buyer).json()["items"] == []
    assert client.post(path, headers=buyer, json={"sku_id": sku["id"], "quantity": 2}).status_code == 200
    before = client.get(path, headers=buyer).json()
    item_id = before["items"][0]["id"]
    for quantity in [0, -1, 21]:
        assert client.post(path, headers=buyer, json={"sku_id": sku["id"], "quantity": quantity}).status_code == 422
        assert client.patch(f"/api/v1/c/cart/{item_id}", headers=buyer, json={"quantity": quantity}).status_code == 422
        assert client.get(path, headers=buyer).json() == before


def test_order_reserves_exact_sku_stock_and_rejects_shortage(client):
    buyer = login(client, "alice")
    path = "/api/v1/c/shops/nanzhi/products"
    product = find(client.get(path).json(), "亚麻抱枕套")
    target, other = product["skus"][:2]
    created = client.post("/api/v1/c/shops/nanzhi/orders", headers=buyer, json={
        "sku_id": target["id"], "quantity": 2, "address": "合成数据验收地址"})
    assert created.status_code == 200, created.text
    after = find(client.get(path).json(), "亚麻抱枕套")
    stocks = {sku["id"]: sku["stock"] for sku in after["skus"]}
    assert stocks[target["id"]] == target["stock"] - 2
    assert stocks[other["id"]] == other["stock"]
    blocked = client.post("/api/v1/c/shops/nanzhi/orders", headers=buyer, json={
        "sku_id": other["id"], "quantity": other["stock"] + 1, "address": "合成数据验收地址"})
    assert blocked.status_code == 400, blocked.text
    assert "库存" in blocked.json()["detail"]
    assert {sku["id"]: sku["stock"] for sku in find(client.get(path).json(), "亚麻抱枕套")["skus"]} == stocks


def test_categories_and_tag_colors_sync_to_buyer(client):
    from test_categories import test_rename_moves_products_to_the_new_name
    from test_tags import test_tag_independent_colors_reach_buyer_and_partial_updates

    test_rename_moves_products_to_the_new_name(client)
    test_tag_independent_colors_reach_buyer_and_partial_updates(client)
