"""分类标签：合集页左侧那排 tag 由商家自己维护。"""

from test_bc_link import find, login


def test_category_names_limit_fifteen_characters_at_all_write_paths(client):
    headers = login(client, "merchant")
    name = "分" * 15
    created = client.post('/api/v1/b/categories', headers=headers, json={'name':name})
    assert created.status_code == 200
    path = f"/api/v1/b/categories/{created.json()['id']}"
    assert client.post('/api/v1/b/categories', headers=headers, json={'name':name+'类'}).status_code == 422
    assert client.patch(path, headers=headers, json={'name':name+'类'}).status_code == 422
    assert client.patch(path, headers=headers, json={'name':'   '}).status_code == 422
    assert client.patch('/api/v1/b/products/1', headers=headers, json={'category':name+'类'}).status_code == 422
    assert client.get('/api/v1/b/categories',headers=headers).json()[-1]['name'] == name


def merchant_categories(client, headers):
    return client.get("/api/v1/b/categories", headers=headers).json()


def test_categories_start_from_seeded_tags(client):
    headers = login(client, "merchant")
    rows = merchant_categories(client, headers)
    names = [row["name"] for row in rows]
    assert names[:4] == ["家居", "餐具", "香氛", "文具"]
    # 每个标签都带商品数，删除按钮要靠它决定能不能点
    assert all(isinstance(row["product_count"], int) for row in rows)
    # 客户端的类目标签顺序和后台一致
    assert client.get("/api/v1/c/shops/nanzhi/categories").json()[:2] == ["家居", "餐具"]


def test_merchant_can_add_rename_and_delete_category(client):
    headers = login(client, "merchant")
    created = client.post("/api/v1/b/categories", headers=headers, json={"name": "茶具"})
    assert created.status_code == 200
    row = created.json()
    assert row["name"] == "茶具" and row["product_count"] == 0

    # 重名直接拒绝，避免标签里出现两条一样的
    assert client.post("/api/v1/b/categories", headers=headers, json={"name": "茶具"}).status_code == 409

    renamed = client.patch(f"/api/v1/b/categories/{row['id']}", headers=headers, json={"name": "茶器"})
    assert renamed.json()["name"] == "茶器"
    assert "茶器" in [item["name"] for item in merchant_categories(client, headers)]

    assert client.delete(f"/api/v1/b/categories/{row['id']}", headers=headers).status_code == 200
    assert "茶器" not in [item["name"] for item in merchant_categories(client, headers)]


def test_rename_moves_products_to_the_new_name(client):
    headers = login(client, "merchant")
    rows = merchant_categories(client, headers)
    home_row = next(row for row in rows if row["name"] == "家居" and row["product_count"] > 0)

    client.patch(f"/api/v1/b/categories/{home_row['id']}", headers=headers, json={"name": "家居好物"})
    listed = client.get("/api/v1/c/shops/nanzhi/products", params={"category": "家居好物"}).json()
    # 统计口径是全部商品，买家端只看到在售的，所以是子集关系
    assert 0 < len(listed) <= home_row["product_count"]
    assert all(item["category"] == "家居好物" for item in listed)
    assert client.get("/api/v1/c/shops/nanzhi/products", params={"category": "家居"}).json() == []
    # 改回原名，不影响后面的用例
    client.patch(f"/api/v1/b/categories/{home_row['id']}", headers=headers, json={"name": "家居"})


def test_category_with_products_cannot_be_deleted(client):
    headers = login(client, "merchant")
    row = next(item for item in merchant_categories(client, headers) if item["product_count"] > 0)
    response = client.delete(f"/api/v1/b/categories/{row['id']}", headers=headers)
    assert response.status_code == 400
    assert str(row["product_count"]) in response.json()["detail"]


def test_sort_order_decides_what_buyers_see_first(client):
    headers = login(client, "merchant")
    rows = merchant_categories(client, headers)
    target = rows[-1]

    # 把它挪到最前面，买家端的标签顺序跟着变
    client.patch(f"/api/v1/b/categories/{target['id']}", headers=headers, json={"sort_order": 1})
    for row in rows[:-1]:
        client.patch(f"/api/v1/b/categories/{row['id']}", headers=headers, json={"sort_order": row["sort_order"] + 1})

    listed = client.get("/api/v1/c/shops/nanzhi/categories").json()
    assert listed[0] == target["name"]

    # 还原，避免影响其他用例
    for row in rows:
        client.patch(f"/api/v1/b/categories/{row['id']}", headers=headers, json={"sort_order": row["sort_order"]})


def test_new_product_category_is_registered_automatically(client):
    headers = login(client, "merchant")
    created = client.post(
        "/api/v1/b/products",
        headers=headers,
        json={
            "name": "手作茶杯",
            "category": "茶器",
            "description": "",
            "image_url": "",
            "skus": [{"spec": "单只", "price_yuan": 49, "stock": 5}],
        },
    )
    assert created.status_code == 200
    assert "茶器" in [row["name"] for row in merchant_categories(client, headers)]

    # 商品下架后从买家端消失，标签本身还在后台
    product = find(client.get("/api/v1/b/products", headers=headers).json(), "手作茶杯")
    client.post(f"/api/v1/b/products/{product['id']}/status", headers=headers, json={"action": "off"})


def test_collection_lists_custom_tags_in_merchant_order(client):
    headers = login(client, "merchant")
    rows = merchant_categories(client, headers)
    data = client.get("/api/v1/c/shops/nanzhi/collections/all").json()
    ordered = [name for name in [row["name"] for row in rows] if data["category_counts"].get(name)]
    assert data["categories"][: len(ordered)] == ordered
    assert data["category_counts"]["家居"] >= 1


def test_category_endpoints_need_merchant_token(client):
    assert client.get("/api/v1/b/categories").status_code == 401
