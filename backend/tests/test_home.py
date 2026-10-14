from test_bc_link import find, login


def test_home_returns_banners_sections_and_testimonials(client):
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    assert [banner["link_type"] for banner in home["banners"]] == ["none", "product", "product"]
    assert home["banners"][0]["image_url"].endswith(".jpg")
    assert home["banners"][0]["title"] == "南枝手作"
    titles = [section["title"] for section in home["sections"]]
    assert titles == ["店主推荐", "畅销榜", "送人体面 · 伴手礼"]
    # 每个栏目最多 6 件
    for section in home["sections"]:
        assert 1 <= len(section["products"]) <= 6
    # 畅销榜按销量降序
    best = next(section for section in home["sections"] if section["title"] == "畅销榜")
    sales = [product["sales_count"] for product in best["products"]]
    assert sales == sorted(sales, reverse=True)
    assert best["products"][0]["name"] == "亚麻抱枕套"
    # 手动栏目保持店主排的顺序
    recommend = home["sections"][0]
    assert [product["name"] for product in recommend["products"]][:2] == ["亚麻抱枕套", "陶瓷马克杯"]
    assert len(home["testimonials"]) == 5
    assert home["shop"]["share_code"] == "nanzhi"


def test_home_hides_下架_and_banned_products(client):
    b_headers = login(client, "merchant")
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    names = {product["name"] for section in home["sections"] for product in section["products"]}
    assert "桌面收纳盒" not in names
    assert "刺绣姓名贴" not in names

    # 把抱枕下架，它应该从推荐位和畅销榜里一起消失
    pillow = find(client.get("/api/v1/b/products", headers=b_headers).json(), "亚麻抱枕套")
    client.post(f"/api/v1/b/products/{pillow['id']}/status", headers=b_headers, json={"action": "off"})
    after = client.get("/api/v1/c/shops/nanzhi/home").json()
    names = {product["name"] for section in after["sections"] for product in section["products"]}
    assert "亚麻抱枕套" not in names


def test_home_is_empty_when_shop_closed(client):
    b_headers = login(client, "merchant")
    client.patch("/api/v1/b/shop", headers=b_headers, json={"status": "closed"})
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    assert home["banners"] == []
    assert home["sections"] == []
    assert home["testimonials"] == []


def test_products_support_paging_for_the_expand_button(client):
    total = len(client.get("/api/v1/c/shops/nanzhi/products").json())
    assert total > 12, "展开按钮需要商品多于三行才有意义"
    first = client.get("/api/v1/c/shops/nanzhi/products", params={"offset": 0, "limit": 12}).json()
    assert len(first) == 12
    second = client.get("/api/v1/c/shops/nanzhi/products", params={"offset": 12, "limit": 12}).json()
    assert len(second) == total - 12
    assert {item["id"] for item in first} & {item["id"] for item in second} == set()
    beyond = client.get("/api/v1/c/shops/nanzhi/products", params={"offset": 200, "limit": 12}).json()
    assert beyond == []


def test_banner_crud_is_scoped_to_the_shop(client):
    headers = login(client, "merchant")
    created = client.post(
        "/api/v1/b/banners",
        headers=headers,
        json={
            "image_url": "/covers/runner.jpg",
            "title": "新到的桌旗",
            "subtitle": "两种长度可选",
            "link_type": "section",
            "link_value": "1",
        },
    )
    assert created.status_code == 200, created.text
    banner_id = created.json()["id"]
    patches = client.patch(f"/api/v1/b/banners/{banner_id}", headers=headers, json={"enabled": False})
    assert patches.json()["enabled"] is False
    listed = client.get("/api/v1/b/banners", headers=headers).json()
    assert [item["id"] for item in listed][-1] == banner_id
    # 停用的图不出现在买家端
    assert banner_id not in {item["id"] for item in client.get("/api/v1/c/shops/nanzhi/home").json()["banners"]}

    client.patch(f"/api/v1/b/banners/{banner_id}", headers=headers, json={"enabled": True})
    assert banner_id in {item["id"] for item in client.get("/api/v1/c/shops/nanzhi/home").json()["banners"]}
    assert client.delete(f"/api/v1/b/banners/{banner_id}", headers=headers).status_code == 200
    assert banner_id not in {item["id"] for item in client.get("/api/v1/b/banners", headers=headers).json()}

    other = client.post(
        "/api/v1/auth/register",
        json={"username": "other2", "password": "other123", "role": "merchant", "nickname": "别家"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.patch(f"/api/v1/b/banners/1", headers=other_headers, json={"title": "偷改"}).status_code == 404


def test_section_crud_controls_home_layout(client):
    headers = login(client, "merchant")
    products = client.get("/api/v1/b/products", headers=headers).json()
    pillow = find(products, "亚麻抱枕套")
    notebook = find(products, "棉麻笔记本")

    created = client.post(
        "/api/v1/b/sections",
        headers=headers,
        json={
            "title": "夏日限定",
            "subtitle": "只在夏天做",
            "source": "manual",
            "product_ids": [notebook["id"], pillow["id"]],
        },
    )
    assert created.status_code == 200, created.text
    section_id = created.json()["id"]
    assert created.json()["product_names"] == ["棉麻笔记本", "亚麻抱枕套"]

    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    custom = next(section for section in home["sections"] if section["id"] == section_id)
    assert custom["title"] == "夏日限定"
    assert [product["name"] for product in custom["products"]] == ["棉麻笔记本", "亚麻抱枕套"]
    assert custom["subtitle"] == "只在夏天做"

    # 改成按销量自动取，顺序会变成销量序
    client.patch(f"/api/v1/b/sections/{section_id}", headers=headers, json={"source": "sales"})
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    custom = next(section for section in home["sections"] if section["id"] == section_id)
    sales = [product["sales_count"] for product in custom["products"]]
    assert sales == sorted(sales, reverse=True)

    # 停用后买家端不再返回
    client.patch(f"/api/v1/b/sections/{section_id}", headers=headers, json={"enabled": False})
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    assert section_id not in {section["id"] for section in home["sections"]}
    assert client.delete(f"/api/v1/b/sections/{section_id}", headers=headers).status_code == 200


def test_testimonial_crud_shows_on_home(client):
    headers = login(client, "merchant")
    created = client.post(
        "/api/v1/b/testimonials",
        headers=headers,
        json={"nickname": "路过", "content": "回购第三次了。", "rating": 5},
    )
    assert created.status_code == 200, created.text
    row_id = created.json()["id"]
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    assert row_id in {row["id"] for row in home["testimonials"]}

    client.patch(f"/api/v1/b/testimonials/{row_id}", headers=headers, json={"enabled": False})
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    assert row_id not in {row["id"] for row in home["testimonials"]}
    assert client.delete(f"/api/v1/b/testimonials/{row_id}", headers=headers).status_code == 200


def test_merchant_can_upload_banner_image(client):
    headers = login(client, "merchant")
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    ok = client.post(
        "/api/v1/b/uploads",
        headers=headers,
        files={"file": ("banner.png", png, "image/png")},
    )
    assert ok.status_code == 200, ok.text
    url = ok.json()["url"]
    assert url.startswith("/covers/uploads/")
    assert client.get(url).status_code == 200

    bad = client.post(
        "/api/v1/b/uploads",
        headers=headers,
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert bad.status_code == 400

    buyer = login(client, "alice")
    assert (
        client.post(
            "/api/v1/b/uploads",
            headers=buyer,
            files={"file": ("banner.png", png, "image/png")},
        ).status_code
        == 403
    )
