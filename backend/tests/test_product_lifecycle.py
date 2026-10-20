from sqlalchemy import create_engine, inspect, text

from app.db.session import SessionLocal
from app.models.tables import Product
from test_bc_link import find, login


def test_sku_order_reaches_buyer_details_and_home(client):
    headers = login(client, "merchant")
    product = find(client.get("/api/v1/b/products", headers=headers).json(), "亚麻抱枕套")
    ids = [sku["id"] for sku in reversed(product["skus"])]
    response = client.post(f"/api/v1/b/products/{product['id']}/skus/sort", headers=headers, json={"ordered_ids": ids})
    assert response.status_code == 200, response.text
    assert [sku["id"] for sku in response.json()["skus"]] == ids
    detail = client.get(f"/api/v1/c/shops/nanzhi/products/{product['id']}").json()
    assert [sku["id"] for sku in detail["skus"]] == ids
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    cards = [item for section in home["sections"] for item in section["products"] if item["id"] == product["id"]]
    assert all([sku["id"] for sku in item["skus"]] == ids for item in cards)
    assert client.post(f"/api/v1/b/products/{product['id']}/skus/sort", headers=headers, json={"ordered_ids": ids[:1]}).status_code == 409
    assert client.post(f"/api/v1/b/products/{product['id']}/skus/sort", headers=headers, json={"ordered_ids": [ids[0], ids[0]]}).status_code == 422
    assert client.post(f"/api/v1/b/products/{product['id']}/skus/sort", headers=login(client, "alice"), json={"ordered_ids": ids}).status_code == 403
    other = find(client.get("/api/v1/b/products", headers=headers).json(), "陶瓷马克杯")
    assert client.post(f"/api/v1/b/products/{other['id']}/skus/sort", headers=headers, json={"ordered_ids": ids}).status_code == 409


def test_banned_product_blocks_all_merchant_writes(client):
    headers = login(client, "merchant")
    product = find(client.get("/api/v1/b/products", headers=headers).json(), "刺绣姓名贴")
    sku_id = product["skus"][0]["id"]
    product_path = f"/api/v1/b/products/{product['id']}"
    assert client.patch(product_path, headers=headers, json={"name": "偷偷修改"}).status_code == 403
    assert client.post(product_path + "/skus", headers=headers, json={"spec": "新规格", "price_yuan": 9, "stock": 1}).status_code == 403
    assert client.patch(f"/api/v1/b/skus/{sku_id}", headers=headers, json={"stock": 999}).status_code == 403
    assert client.post(product_path + "/skus/sort", headers=headers, json={"ordered_ids": [sku_id]}).status_code == 403
    for action in ("on", "off", "ban", "unban"):
        assert client.post(product_path + "/status", headers=headers, json={"action": action}).status_code == 403
        assert client.post(f"/api/v1/b/skus/{sku_id}/status", headers=headers, json={"action": action}).status_code == 403
    assert find(client.get("/api/v1/b/products", headers=headers).json(), "刺绣姓名贴") == product


def test_draft_only_initial_state_and_no_extra_draft_table(client):
    headers = login(client, "merchant")
    created = client.post("/api/v1/b/products", headers=headers, json={"name": "草稿商品"}).json()
    assert created["status"] == "draft" and not created["skus"]
    drafts = client.get("/api/v1/b/products?status=draft", headers=headers).json()
    assert [product["id"] for product in drafts] == [created["id"]]
    path = f"/api/v1/b/products/{created['id']}"
    assert client.get(f"/api/v1/c/shops/nanzhi/products/{created['id']}").status_code == 404
    assert client.post(path + "/status", headers=headers, json={"action": "on"}).status_code == 400
    assert client.post(path + "/skus", headers=headers, json={"spec": "标准", "price_yuan": 20, "stock": 3}).status_code == 200
    assert client.post(path + "/status", headers=headers, json={"action": "off"}).json()["status"] == "off"
    assert client.post(path + "/status", headers=headers, json={"action": "draft"}).status_code == 422
    assert client.post(path + "/status", headers=headers, json={"action": "on"}).json()["status"] == "on"
    assert client.get(f"/api/v1/c/shops/nanzhi/products/{created['id']}").status_code == 200
    with SessionLocal() as db:
        assert db.get(Product, created["id"]).status == "on"
        assert not any("draft" in name for name in inspect(db.bind).get_table_names())


def test_sku_sort_order_upgrade_preserves_existing_rows(monkeypatch):
    import app.main as main
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE skus (id INTEGER PRIMARY KEY, spec VARCHAR(64))")
        connection.exec_driver_sql("INSERT INTO skus (id, spec) VALUES (1, '原规格')")
    monkeypatch.setattr(main, "engine", engine)
    main._ensure_sku_sort_order()
    main._ensure_sku_sort_order()
    with engine.connect() as connection:
        row = connection.execute(text("SELECT id, spec, sort_order FROM skus")).one()
        assert tuple(row) == (1, "原规格", 0)
    engine.dispose()
