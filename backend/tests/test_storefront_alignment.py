from test_bc_link import login


def test_storefront_settings_roundtrip_and_partial_preserves(client):
    headers = login(client, "merchant")
    response = client.patch("/api/v1/b/shop", headers=headers, json={"storefront": {
        "background_color": "#efe4d4", "surface_color": "#f9f4e9", "rail_columns": "4",
        "product_image_ratio": "3/4", "hero_enabled": False, "assistant_enabled": False,
        "assistant_welcome": "欢迎选购本店商品", "quick_questions": [],
        "detail_sections": [{"title": "包装", "body": "请在下单前确认包装要求"}],
    }})
    assert response.status_code == 200, response.text
    settings = response.json()["storefront"]
    public = client.get("/api/v1/c/shops/nanzhi").json()
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    assert settings == public["storefront"] == home["shop"]["storefront"]
    changed = client.patch("/api/v1/b/shop", headers=headers, json={"storefront": {"footer_about": "商家修改的简介"}}).json()
    assert changed["storefront"]["background_color"] == "#efe4d4"
    assert changed["storefront"]["footer_about"] == "商家修改的简介"


def test_settings_validation_and_shop_isolation(client):
    headers = login(client, "merchant")
    for config in ({"background_color": "red;display:none"}, {"rail_columns": "100"},
                   {"base_freight_yuan": -1}, {"base_freight_yuan": 8.005}, {"quick_questions": ["a" * 81]},
                   {"unknown_setting": "x"}):
        assert client.patch("/api/v1/b/shop", headers=headers, json={"storefront": config}).status_code == 422
    assert client.patch("/api/v1/b/shop", headers=login(client, "alice"), json={"storefront": {"background_color": "#123456"}}).status_code == 403
    client.post("/api/v1/auth/register", json={"username": "othermerchant", "password": "123456", "role": "merchant"})
    other = client.patch("/api/v1/b/shop", headers=login(client, "othermerchant", "123456"), json={"storefront": {"background_color": "#112233"}})
    assert other.status_code == 200
    assert client.get("/api/v1/c/shops/nanzhi").json()["storefront"]["background_color"] != "#112233"


def test_freight_quote_cart_and_created_order_use_same_shop_rules(client):
    headers = login(client, "merchant")
    buyer = login(client, "alice")
    updated = client.patch("/api/v1/b/shop", headers=headers, json={"storefront": {"free_shipping_yuan": 200, "base_freight_yuan": 15}})
    assert updated.status_code == 200
    sku = client.get("/api/v1/c/shops/nanzhi/products").json()[0]["skus"][0]
    client.post("/api/v1/c/shops/nanzhi/cart", headers=buyer, json={"sku_id": sku["id"], "quantity": 1})
    cart = client.get("/api/v1/c/shops/nanzhi/cart", headers=buyer).json()
    assert cart["freight_yuan"] == 15
    quoted = client.post("/api/v1/c/shops/nanzhi/coupon-quote", headers=buyer, json={"items": [{"sku_id": sku["id"], "quantity": 1}]}).json()
    assert quoted["freight_yuan"] == 15
    order = client.post("/api/v1/c/shops/nanzhi/orders", headers=buyer,
                        json={"sku_id": sku["id"], "quantity": 1, "address": "测试地址四个字"}).json()
    assert order["freight_yuan"] == 15
    client.patch("/api/v1/b/shop", headers=headers, json={"storefront": {"base_freight_yuan": 0}})
    orders = client.get("/api/v1/c/orders", headers=buyer, params={"share_code": "nanzhi"}).json()
    assert next(item for item in orders if item["order_no"] == order["order_no"])["freight_yuan"] == 15
    quote = client.post("/api/v1/c/shops/nanzhi/coupon-quote", headers=buyer, json={"items": [{"sku_id": sku["id"], "quantity": 1}]}).json()
    assert quote["freight_yuan"] == 0


def test_clear_market_price_and_cart_uses_sku_image(client):
    headers = login(client, "merchant")
    buyer = login(client, "alice")
    product = client.get("/api/v1/b/products", headers=headers).json()[0]
    sku = product["skus"][0]
    response = client.patch(f"/api/v1/b/skus/{sku['id']}", headers=headers,
                            json={"market_price_yuan": None, "image_url": "/covers/sku-specific.jpg"})
    assert response.status_code == 200
    public = client.get(f"/api/v1/c/shops/nanzhi/products/{product['id']}").json()
    assert public["skus"][0]["market_price_yuan"] is None
    client.post("/api/v1/c/shops/nanzhi/cart", headers=buyer, json={"sku_id": sku["id"], "quantity": 1})
    cart = client.get("/api/v1/c/shops/nanzhi/cart", headers=buyer).json()
    assert next(item for item in cart["items"] if item["sku_id"] == sku["id"])["image_url"] == "/covers/sku-specific.jpg"


def test_card_market_price_belongs_to_starting_sku(client):
    headers = login(client, "merchant")
    product = client.post("/api/v1/b/products", headers=headers, json={
        "name": "多规格价格对齐测试", "skus": [
            {"spec": "单只", "price_yuan": 49, "stock": 10},
            {"spec": "两只装", "price_yuan": 88, "market_price_yuan": 98, "stock": 10},
        ],
    }).json()
    assert product["price_from"] == 49 and product["market_from"] is None
    client.post(f"/api/v1/b/products/{product['id']}/status", headers=headers, json={"action": "on"})
    public = client.get(f"/api/v1/c/shops/nanzhi/products/{product['id']}").json()
    assert public["price_from"] == 49 and public["market_from"] is None


def test_appearance_form_default_shipping_promise_tracks_new_rules(client):
    headers = login(client, "merchant")
    settings = client.get("/api/v1/b/shop", headers=headers).json()
    response = client.patch("/api/v1/b/shop", headers=headers, json={
        "promises": settings["promises"], "storefront": {"free_shipping_yuan": 200, "base_freight_yuan": 15,
            "dispatch_text": "付款后7天内发货", "return_text": "仅未拆封商品支持退换"},
    })
    assert response.status_code == 200
    assert {"title": "满 200 包邮", "sub": "未满收 15 元运费"} in response.json()["promises"]
    assert {"title": "发货说明", "sub": "付款后7天内发货"} in response.json()["promises"]
    assert {"title": "退换说明", "sub": "仅未拆封商品支持退换"} in response.json()["promises"]
    reset = client.patch("/api/v1/b/shop", headers=headers, json={"promises": []})
    assert {"title": "满 200 包邮", "sub": "未满收 15 元运费"} in reset.json()["promises"]


def test_large_shipping_values_not_rounded_in_labels():
    from app.schemas.storefront import StorefrontSettings
    from app.services.storefront import shipping_promise
    assert shipping_promise(StorefrontSettings(free_shipping_yuan=19999.99))["title"] == "满 19999.99 包邮"
