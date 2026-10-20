from merchant_fixture import authorize_merchant
from test_bc_link import find, login


def test_collection_all_returns_full_catalog(client):
    page = client.get("/api/v1/c/shops/nanzhi/collections/all").json()
    assert page["key"] == "all"
    assert page["title"] == "全部商品"
    listed = client.get("/api/v1/c/shops/nanzhi/products").json()
    assert page["total"] == len(listed)
    assert len(page["products"]) == len(listed)
    # 左侧筛选用的类目来自这批商品
    assert set(page["categories"]) == {item["category"] for item in listed}
    assert page["category_counts"]["家居"] == len([item for item in listed if item["category"] == "家居"])
    # 下架和禁售的不在里面
    names = {item["name"] for item in page["products"]}
    assert "桌面收纳盒" not in names and "刺绣姓名贴" not in names


def test_collection_matches_its_section_and_is_not_capped(client):
    home = client.get("/api/v1/c/shops/nanzhi/home").json()
    recommend = next(s for s in home["sections"] if s["title"] == "店主推荐")
    assert len(recommend["products"]) == 6  # 首页只给 6 件

    page = client.get(f"/api/v1/c/shops/nanzhi/collections/{recommend['id']}").json()
    assert page["title"] == "店主推荐"
    # 合集页给的是这个栏目的全量，和首页顺序一致
    home_ids = [item["id"] for item in recommend["products"]]
    page_ids = [item["id"] for item in page["products"]]
    assert page_ids[: len(home_ids)] == home_ids
    assert page["total"] >= len(home_ids)


def test_collection_supports_category_keyword_and_sort(client):
    page = client.get("/api/v1/c/shops/nanzhi/collections/all", params={"category": "家居"}).json()
    assert page["products"]
    assert {item["category"] for item in page["products"]} == {"家居"}
    assert page["total"] > len(page["products"])  # total 是合集本身的数量

    hit = client.get("/api/v1/c/shops/nanzhi/collections/all", params={"keyword": "亚麻"}).json()
    assert hit["products"]
    assert all("亚麻" in item["name"] or "亚麻" in item["category"] for item in hit["products"])

    asc = client.get("/api/v1/c/shops/nanzhi/collections/all", params={"sort": "price_asc"}).json()
    prices = [item["price_from"] for item in asc["products"]]
    assert prices == sorted(prices)
    desc = client.get("/api/v1/c/shops/nanzhi/collections/all", params={"sort": "price_desc"}).json()
    desc_prices = [item["price_from"] for item in desc["products"]]
    assert desc_prices == sorted(desc_prices, reverse=True)

    sales = client.get("/api/v1/c/shops/nanzhi/collections/all", params={"sort": "sales"}).json()
    counts = [item["sales_count"] for item in sales["products"]]
    assert counts == sorted(counts, reverse=True)


def test_collection_404_for_unknown_or_foreign_section(client):
    assert client.get("/api/v1/c/shops/nanzhi/collections/99999").status_code == 404
    assert client.get("/api/v1/c/shops/nanzhi/collections/abc").status_code == 404

    other = client.post(
        "/api/v1/auth/register",
        json={"username": "otherc", "password": "other123", "role": "merchant", "nickname": "别家"},
    )
    authorize_merchant(client, other)
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    foreign = client.post(
        "/api/v1/b/sections",
        headers=headers,
        json={"title": "别家的栏目", "source": "manual", "product_ids": []},
    ).json()
    # 别家店的栏目编号在本店查不到
    assert client.get(f"/api/v1/c/shops/nanzhi/collections/{foreign['id']}").status_code == 404


def test_collection_hides_everything_when_shop_closed(client):
    merchant = login(client, "merchant")
    client.patch("/api/v1/b/shop", headers=merchant, json={"status": "closed"})
    page = client.get("/api/v1/c/shops/nanzhi/collections/all").json()
    assert page["products"] == []
    assert page["total"] == 0


def test_collection_is_the_same_for_everyone(client):
    """合集页的商品列表不再带因人而异的状态，登录与否看到的是同一份。"""
    alice = login(client, "alice")
    pillow = find(client.get("/api/v1/c/shops/nanzhi/products").json(), "亚麻抱枕套")
    with_user = client.get("/api/v1/c/shops/nanzhi/collections/all", headers=alice).json()
    anonymous = client.get("/api/v1/c/shops/nanzhi/collections/all").json()
    assert with_user["products"] == anonymous["products"]
    assert "favorited" not in next(item for item in with_user["products"] if item["id"] == pillow["id"])
