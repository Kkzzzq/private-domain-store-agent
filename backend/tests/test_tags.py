"""商品标签和首页外观：这两个都是商家在后台配、买家端立刻能看到的。"""

from test_bc_link import find, login


def merchant_tags(client, headers):
    return client.get("/api/v1/b/tags", headers=headers).json()


def test_tags_start_from_seeded_library(client):
    headers = login(client, "merchant")
    rows = merchant_tags(client, headers)
    names = [row["name"] for row in rows]
    assert names[:4] == ["促销", "爆款", "新上线", "折扣"]
    # 每个标签都带底色和商品数，样式和删除确认都要用
    assert all(row["color"].startswith("#") for row in rows)
    assert all(isinstance(row["product_count"], int) for row in rows)
    assert sum(row["product_count"] for row in rows) >= 4


def test_buyer_card_carries_merchant_tags(client):
    listed = client.get("/api/v1/c/shops/nanzhi/products").json()
    pillow = next(item for item in listed if item["name"] == "亚麻抱枕套")
    # 演示数据给抱枕挂了「爆款 + 折扣」，卡上显示排最前的那个
    assert [tag["name"] for tag in pillow["tags"]] == ["爆款", "折扣"]
    assert pillow["tags"][0]["color"] == "#e5484d"


def test_product_without_tags_falls_back_to_nothing(client):
    listed = client.get("/api/v1/c/shops/nanzhi/products").json()
    runner = next(item for item in listed if item["name"] == "亚麻桌旗")
    assert runner["tags"] == []


def test_create_rename_and_delete_tag(client):
    headers = login(client, "merchant")
    created = client.post("/api/v1/b/tags", headers=headers, json={"name": "清仓", "color": "#3366ff"})
    assert created.status_code == 200
    row = created.json()
    assert row["color"] == "#3366ff" and row["product_count"] == 0

    assert client.post("/api/v1/b/tags", headers=headers, json={"name": "清仓"}).status_code == 409

    renamed = client.patch(f"/api/v1/b/tags/{row['id']}", headers=headers, json={"name": "限时清仓"})
    assert renamed.json()["name"] == "限时清仓"

    assert client.delete(f"/api/v1/b/tags/{row['id']}", headers=headers).status_code == 200
    assert "限时清仓" not in [item["name"] for item in merchant_tags(client, headers)]


def test_rename_tag_keeps_products_attached(client):
    headers = login(client, "merchant")
    row = next(item for item in merchant_tags(client, headers) if item["name"] == "促销" and item["product_count"])

    client.patch(f"/api/v1/b/tags/{row['id']}", headers=headers, json={"name": "限时促销"})
    listed = client.get("/api/v1/c/shops/nanzhi/products").json()
    tagged = [item for item in listed if any(tag["name"] == "限时促销" for tag in item["tags"])]
    # 关联表存的是标签 id，改名后商品自动跟着改，数量不变
    assert len(tagged) == row["product_count"]

    client.patch(f"/api/v1/b/tags/{row['id']}", headers=headers, json={"name": "促销"})


def test_delete_tag_detaches_products(client):
    headers = login(client, "merchant")
    created = client.post("/api/v1/b/tags", headers=headers, json={"name": "临时"}).json()
    products = client.get("/api/v1/b/products", headers=headers).json()
    target = products[0]

    client.patch(f"/api/v1/b/products/{target['id']}", headers=headers, json={"tag_names": ["临时"]})
    assert "临时" in [tag["name"] for tag in find(client.get("/api/v1/b/products", headers=headers).json(), target["name"])["tags"]]

    client.delete(f"/api/v1/b/tags/{created['id']}", headers=headers)
    after = find(client.get("/api/v1/b/products", headers=headers).json(), target["name"])
    assert "临时" not in [tag["name"] for tag in after["tags"]]


def test_tag_order_decides_which_badge_shows(client):
    headers = login(client, "merchant")
    rows = merchant_tags(client, headers)
    # 把「折扣」挪到最前，抱枕卡上的角标就该变成折扣
    for index, row in enumerate(sorted(rows, key=lambda item: item["sort_order"], reverse=True)):
        client.patch(f"/api/v1/b/tags/{row['id']}", headers=headers, json={"sort_order": index + 1})

    listed = client.get("/api/v1/c/shops/nanzhi/products").json()
    pillow = next(item for item in listed if item["name"] == "亚麻抱枕套")
    assert pillow["tags"][0]["name"] == "折扣"

    for row in rows:
        client.patch(f"/api/v1/b/tags/{row['id']}", headers=headers, json={"sort_order": row["sort_order"]})


def test_product_saves_tag_names_and_creates_missing_ones(client):
    headers = login(client, "merchant")
    created = client.post(
        "/api/v1/b/products",
        headers=headers,
        json={
            "name": "手作茶杯",
            "category": "餐具",
            "description": "",
            "image_url": "",
            "tag_names": ["新品", "促销"],
            "skus": [{"spec": "单只", "price_yuan": 49, "stock": 5}],
        },
    )
    assert created.status_code == 200
    # 挂着几个都存下来，但顺序听标签库的（促销排在 新品 前面），卡片取第一个
    assert [tag["name"] for tag in created.json()["tags"]] == ["促销", "新品"]
    # 现场填的「新品」自动进了标签库
    assert "新品" in [row["name"] for row in merchant_tags(client, headers)]

    product = find(client.get("/api/v1/b/products", headers=headers).json(), "手作茶杯")
    updated = client.patch(f"/api/v1/b/products/{product['id']}", headers=headers, json={"tag_names": ["新品"]})
    assert [tag["name"] for tag in updated.json()["tags"]] == ["新品"]


def test_product_tag_limit_is_enforced(client):
    headers = login(client, "merchant")
    products = client.get("/api/v1/b/products", headers=headers).json()
    response = client.patch(
        f"/api/v1/b/products/{products[0]['id']}",
        headers=headers,
        json={"tag_names": ["a", "b", "c", "d", "e"]},
    )
    assert response.status_code == 422


def test_shop_appearance_reaches_the_buyer(client):
    headers = login(client, "merchant")
    before = client.get("/api/v1/c/shops/nanzhi").json()
    assert before["hero_height"] == 640
    assert before["strip_tint"] is True
    # 没自己写的时候用默认那四条
    assert [row["title"] for row in before["promises"]] == ["正品保障", "7 天无理由", "满 99 包邮", "48 小时发货"]

    client.patch("/api/v1/b/shop", headers=headers, json={"hero_height": 460, "strip_tint": False})
    after = client.get("/api/v1/c/shops/nanzhi").json()
    assert after["hero_height"] == 460 and after["strip_tint"] is False

    # 超范围的高度直接拒绝，免得买家端被撑坏
    assert client.patch("/api/v1/b/shop", headers=headers, json={"hero_height": 2000}).status_code == 422

    client.patch("/api/v1/b/shop", headers=headers, json={"hero_height": 640, "strip_tint": True})


def test_merchant_can_rewrite_the_promise_bar(client):
    headers = login(client, "merchant")
    rows = [
        {"title": "顺丰包邮", "sub": "48 小时内发出"},
        {"title": "假一赔十", "sub": "店主自己发货"},
    ]
    client.patch("/api/v1/b/shop", headers=headers, json={"promises": rows})
    listed = client.get("/api/v1/c/shops/nanzhi").json()["promises"]
    assert listed == rows

    # 清空就回到默认那四条，首页不会出现空白的一条
    client.patch("/api/v1/b/shop", headers=headers, json={"promises": []})
    assert len(client.get("/api/v1/c/shops/nanzhi").json()["promises"]) == 4

    # 超过 6 条直接拒绝
    too_many = [{"title": f"第 {i} 条", "sub": ""} for i in range(7)]
    assert client.patch("/api/v1/b/shop", headers=headers, json={"promises": too_many}).status_code == 422


def test_tag_endpoints_need_merchant_token(client):
    assert client.get("/api/v1/b/tags").status_code == 401
