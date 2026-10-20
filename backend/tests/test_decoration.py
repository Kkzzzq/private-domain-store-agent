from copy import deepcopy

from test_bc_link import login


def snapshot(client, headers):
    response = client.get("/api/v1/b/decoration", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_is_read_only_and_save_publishes_all(client):
    headers = login(client, "merchant")
    original = snapshot(client, headers)
    draft = deepcopy(original)
    draft["appearance"]["storefront"]["background_color"] = "#efe4d4"
    draft["banners"][0]["title"] = "仅草稿可见"
    draft["banners"].reverse()
    draft["sections"].reverse()
    preview = client.post("/api/v1/b/decoration/preview", headers=headers, json=draft)
    assert preview.status_code == 200, preview.text
    assert preview.json()["home"]["shop"]["storefront"]["background_color"] == "#efe4d4"
    assert any(row["title"] == "仅草稿可见" for row in preview.json()["home"]["banners"])
    assert snapshot(client, headers) == original
    before = client.get("/api/v1/c/shops/nanzhi/home").json()
    assert not any(row["title"] == "仅草稿可见" for row in before["banners"])
    saved = client.put("/api/v1/b/decoration", headers=headers, json=draft)
    assert saved.status_code == 200, saved.text
    after = client.get("/api/v1/c/shops/nanzhi/home").json()
    assert after["shop"]["storefront"]["background_color"] == "#efe4d4"
    assert [row["id"] for row in after["banners"]] == [row["id"] for row in draft["banners"] if row["enabled"]]
    assert saved.json()["revision"] != original["revision"]


def test_draft_new_section_and_banner_link_remap(client):
    headers = login(client, "merchant")
    draft = snapshot(client, headers)
    product = client.get("/api/v1/b/products", headers=headers).json()[0]
    draft["sections"].append({"id": -1, "title": "新栏目", "subtitle": "", "source": "manual", "enabled": True, "product_ids": [product["id"]]})
    draft["banners"].append({"id": -1, "title": "新轮播", "subtitle": "", "image_url": "/covers/pillow.jpg", "link_type": "section", "link_value": "-1", "enabled": True})
    response = client.put("/api/v1/b/decoration", headers=headers, json=draft)
    assert response.status_code == 200, response.text
    saved = response.json()
    section = next(row for row in saved["sections"] if row["title"] == "新栏目")
    banner = next(row for row in saved["banners"] if row["title"] == "新轮播")
    assert section["id"] > 0
    assert banner["link_value"] == str(section["id"])
    assert section["product_ids"] == [product["id"]]


def test_invalid_scope_or_link_does_not_partially_save(client):
    headers = login(client, "merchant")
    original = snapshot(client, headers)
    for kind in ("sections", "banners"):
        draft = deepcopy(original)
        draft["appearance"]["storefront"]["background_color"] = "#123456"
        if kind == "sections":
            draft["sections"][0]["product_ids"] = [999999]
        else:
            draft["banners"][0]["link_type"] = "section"
            draft["banners"][0]["link_value"] = "999999"
        assert client.put("/api/v1/b/decoration", headers=headers, json=draft).status_code == 422
        assert snapshot(client, headers) == original
    draft = deepcopy(original)
    draft["banners"][0]["id"] = 999999
    assert client.post("/api/v1/b/decoration/preview", headers=headers, json=draft).status_code == 409
    assert snapshot(client, headers) == original


def test_stale_revision_rejected_and_deletions_supported(client):
    headers = login(client, "merchant")
    draft = snapshot(client, headers)
    stale = deepcopy(draft)
    draft["testimonials"] = []
    assert client.put("/api/v1/b/decoration", headers=headers, json=draft).status_code == 200
    assert client.get("/api/v1/c/shops/nanzhi/home").json()["testimonials"] == []
    assert client.put("/api/v1/b/decoration", headers=headers, json=stale).status_code == 409


def test_existing_section_product_replacement_returns_fresh_snapshot(client):
    headers = login(client, "merchant")
    draft = snapshot(client, headers)
    products = client.get("/api/v1/b/products", headers=headers).json()
    target = products[-1]["id"]
    section = next(row for row in draft["sections"] if row["source"] == "manual")
    section["product_ids"] = [target]
    response = client.put("/api/v1/b/decoration", headers=headers, json=draft)
    assert response.status_code == 200, response.text
    returned = next(row for row in response.json()["sections"] if row["id"] == section["id"])
    assert returned["product_ids"] == [target]
    assert response.json() == snapshot(client, headers)


def test_reorder_atomic_complete_list_and_permissions(client):
    headers = login(client, "merchant")
    for kind in ("categories", "tags", "banners", "sections", "testimonials"):
        original = client.get(f"/api/v1/b/{kind}", headers=headers).json()
        ids = [row["id"] for row in reversed(original)]
        response = client.post(f"/api/v1/b/sort/{kind}", headers=headers, json={"ordered_ids": ids})
        assert response.status_code == 200, response.text
        assert [row["id"] for row in client.get(f"/api/v1/b/{kind}", headers=headers).json()] == ids
        assert client.post(f"/api/v1/b/sort/{kind}", headers=headers, json={"ordered_ids": ids[:-1]}).status_code == 409
        assert client.post(f"/api/v1/b/sort/{kind}", headers=headers, json={"ordered_ids": [999999] + ids}).status_code == 409
        assert client.post(f"/api/v1/b/sort/{kind}", headers=headers, json={"ordered_ids": ids + ids}).status_code == 422
    buyer = login(client, "alice")
    assert client.get("/api/v1/b/decoration", headers=buyer).status_code == 403
    assert client.post("/api/v1/b/sort/tags", headers=buyer, json={"ordered_ids": []}).status_code == 403
