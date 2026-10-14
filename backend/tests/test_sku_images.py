"""规格图：详情页切规格（或点缩略图）时主图跟着换要用的数据。"""

from test_bc_link import find, login


def test_buyer_sees_one_image_per_sku(client):
    product = client.get("/api/v1/c/shops/nanzhi/products/1").json()
    assert [sku["spec"] for sku in product["skus"]] == ["米白", "雾蓝"]
    assert [sku["image_url"] for sku in product["skus"]] == ["/covers/pillow.jpg", "/covers/pillow-blue.jpg"]


def test_sku_without_image_falls_back_on_the_client(client):
    # 笔记本只有第一个规格配了图，第二个留空，前端会退回商品主图
    listed = client.get("/api/v1/c/shops/nanzhi/products").json()
    notebook = find(listed, "棉麻笔记本")
    detail = client.get(f"/api/v1/c/shops/nanzhi/products/{notebook['id']}").json()
    assert detail["skus"][0]["image_url"] == "/covers/notebook.jpg"
    assert detail["skus"][1]["image_url"] == ""


def test_merchant_can_set_a_sku_image(client):
    headers = login(client, "merchant")
    product = find(client.get("/api/v1/b/products", headers=headers).json(), "棉麻笔记本")
    sku = product["skus"][1]

    updated = client.patch(f"/api/v1/b/skus/{sku['id']}", headers=headers, json={"image_url": "/covers/box.jpg"})
    assert updated.status_code == 200
    rows = {row["id"]: row for row in updated.json()["skus"]}
    assert rows[sku["id"]]["image_url"] == "/covers/box.jpg"
    # 买家端详情页拿到的是同一份数据
    detail = client.get(f"/api/v1/c/shops/nanzhi/products/{product['id']}").json()
    assert {row["id"]: row["image_url"] for row in detail["skus"]}[sku["id"]] == "/covers/box.jpg"

    client.patch(f"/api/v1/b/skus/{sku['id']}", headers=headers, json={"image_url": ""})
    assert client.get(f"/api/v1/c/shops/nanzhi/products/{product['id']}").json()["skus"][1]["image_url"] == ""


def test_new_sku_can_carry_an_image(client):
    headers = login(client, "merchant")
    product = find(client.get("/api/v1/b/products", headers=headers).json(), "陶瓷马克杯")
    created = client.post(
        f"/api/v1/b/products/{product['id']}/skus",
        headers=headers,
        json={"spec": "对杯", "price_yuan": 69, "stock": 4, "image_url": "/covers/mug-detail.jpg"},
    )
    assert created.status_code == 200
    added = next(row for row in created.json()["skus"] if row["spec"] == "对杯")
    assert added["image_url"] == "/covers/mug-detail.jpg"

    # 清掉，免得影响别的用例
    client.post(f"/api/v1/b/skus/{added['id']}/status", headers=headers, json={"action": "off"})


def test_saved_lists_carry_sku_images(client):
    alice = login(client, "alice")
    client.post("/api/v1/c/favorites/1", headers=alice)
    rows = client.get("/api/v1/c/favorites", headers=alice).json()
    pillow = find(rows, "亚麻抱枕套")
    assert pillow["skus"][0]["image_url"] == "/covers/pillow.jpg"

    client.post("/api/v1/c/favorites/1", headers=alice)


def test_product_creation_accepts_sku_images(client):
    headers = login(client, "merchant")
    created = client.post(
        "/api/v1/b/products",
        headers=headers,
        json={
            "name": "手作茶壶",
            "category": "餐具",
            "description": "",
            "image_url": "/covers/mug.jpg",
            "skus": [{"spec": "素白", "price_yuan": 88, "stock": 3, "image_url": "/covers/mug-detail.jpg"}],
        },
    )
    assert created.status_code == 200
    assert created.json()["skus"][0]["image_url"] == "/covers/mug-detail.jpg"
