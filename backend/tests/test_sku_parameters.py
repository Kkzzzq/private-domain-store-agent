from merchant_fixture import authorize_merchant
from test_bc_link import login


def test_parameters_optional_saved_visible_and_clearable(client):
    merchant = login(client, "merchant")
    product = client.get("/api/v1/c/shops/nanzhi/products/1").json()
    sku = product["skus"][0]
    assert sku["parameters"] == []
    values = [{"name": " 面料 ", "value": " 棉麻 "}, {"name": "尺寸", "value": "45 × 45 cm"}]
    path = f"/api/v1/b/skus/{sku['id']}"
    response = client.patch(path, headers=merchant, json={"parameters": values})
    assert response.status_code == 200
    expected = [{"name": "面料", "value": "棉麻"}, values[1]]
    assert client.get("/api/v1/c/shops/nanzhi/products/1").json()["skus"][0]["parameters"] == expected
    client.patch(path, headers=merchant, json={"stock": 9})
    assert client.get("/api/v1/c/shops/nanzhi/products/1").json()["skus"][0]["parameters"] == expected
    assert client.patch(path, headers=merchant, json={"parameters": []}).status_code == 200
    assert client.get("/api/v1/c/shops/nanzhi/products/1").json()["skus"][0]["parameters"] == []


def test_parameter_validation_and_customer_cannot_edit(client):
    merchant = login(client, "merchant")
    sku = client.get("/api/v1/c/shops/nanzhi/products/1").json()["skus"][0]
    path = f"/api/v1/b/skus/{sku['id']}"
    for values in ([{"name": " ", "value": "x"}], [{"name": "x", "value": "v"}] * 13):
        assert client.patch(path, headers=merchant, json={"parameters": values}).status_code == 422
    assert client.patch(path, headers=login(client, "alice"), json={"parameters": []}).status_code == 403


def test_new_sku_accepts_parameters(client):
    response = client.post("/api/v1/b/products/1/skus", headers=login(client, "merchant"), json={
        "spec": "参数测试", "price_yuan": 39, "stock": 2,
        "parameters": [{"name": "材质", "value": "棉"}],
    })
    assert response.status_code == 200
    added = next(sku for sku in response.json()["skus"] if sku["spec"] == "参数测试")
    assert added["parameters"] == [{"name": "材质", "value": "棉"}]


def test_other_merchant_cannot_set_parameters(client):
    other = client.post("/api/v1/auth/register", json={"username": "param_other", "password": "other123", "role": "merchant"}).json()
    authorize_merchant(client, other)
    headers = {"Authorization": "Bearer " + other["access_token"]}
    sku = client.get("/api/v1/c/shops/nanzhi/products/1").json()["skus"][0]
    response = client.patch(f"/api/v1/b/skus/{sku['id']}", headers=headers, json={"parameters": [{"name": "x", "value": "y"}]})
    assert response.status_code == 404
