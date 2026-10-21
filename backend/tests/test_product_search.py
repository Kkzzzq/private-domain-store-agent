from app.services.product_search import documents, search_rows


def sample_rows():
    return [{"id": 7, "name": "轻柔盖毯", "category": "家居", "description": "适合午休盖在身上。",
             "tags": ["新品"], "skus": [{"id": 71, "spec": "雾蓝", "parameters": [{"name": "面料", "value": "竹纤维"}], "price_yuan": 80, "stock": 2},
                                      {"id": 72, "spec": "米白", "parameters": [], "price_yuan": 90, "stock": 0}]}]


def test_full_fields_and_sku_precise_matches():
    rows = sample_rows()
    for term in ("午休", "新品", "家居"):
        assert search_rows(term, rows, None, None)
    matched = search_rows("竹纤维", rows, None, None)
    assert [sku["id"] for sku in matched[0]["skus"]] == [71]
    assert [sku["id"] for sku in search_rows("雾蓝", rows, None, None)[0]["skus"]] == [71]


def test_synonym_does_not_equate_pillow_with_quilt():
    from app.services.product_search import literal_match
    assert literal_match("被子", "双人羽绒被")
    assert not literal_match("被子", "亚麻抱枕套")


def test_chunks_cover_long_description_and_all_skus_without_stock_price():
    rows = sample_rows()
    rows[0]["description"] = "长描述" * 2000 + "尾部完整描述"
    chunks = documents(rows)
    assert {chunk["heading_path"] for chunk in chunks} == {"71", "72"}
    assert any("尾部完整描述" in chunk["content"] for chunk in chunks)
    assert all("price_yuan" not in chunk["content"] and "stock" not in chunk["content"] for chunk in chunks)


def test_semantic_candidates_are_intersected_with_current_database_rows(monkeypatch):
    monkeypatch.setattr("app.services.product_search.semantic_matches", lambda *args: {(7, 71), (999, 999)})
    found = search_rows("盖着睡觉", sample_rows(), None, None)
    assert [row["id"] for row in found] == [7]
    assert [sku["id"] for sku in found[0]["skus"]] == [71]


def test_agent_search_uses_description_and_sku_but_hides_off_products(client):
    from sqlalchemy import select
    from app.agent.context import Actor, reset_actor, set_actor
    from app.agent.guard import execute_tool
    from app.db.session import SessionLocal
    from app.models.tables import Product, Sku, User
    with SessionLocal() as db:
        buyer = db.scalar(select(User).where(User.username == "alice"))
        db.add(Product(shop_id=1, name="轻柔盖毯", category="家居", description="独有午休材质",
                       status="on", skus=[Sku(spec="雾蓝大号", price_cents=8000, stock=2)]))
        db.add(Product(shop_id=1, name="隐藏独有午休", category="家居", status="off",
                       skus=[Sku(spec="雾蓝大号", price_cents=100, stock=2)]))
        db.commit()
        token = set_actor(db, Actor(buyer.id, "customer", buyer.username, 1))
        try:
            for keyword in ("独有午休", "雾蓝大号"):
                result = execute_tool("search_products", {"keyword": keyword})
                assert "轻柔盖毯" in result and "隐藏独有午休" not in result
        finally:
            reset_actor(token)


def test_vector_candidates_do_not_override_current_product_status(client, monkeypatch):
    from sqlalchemy import select
    from app.agent.context import Actor, reset_actor, set_actor
    from app.agent.guard import execute_tool
    from app.db.session import SessionLocal
    from app.models.tables import Product, Sku, User
    with SessionLocal() as db:
        buyer = db.scalar(select(User).where(User.username == "alice"))
        product = Product(shop_id=1, name="即时变更测试", category="家居", status="on",
                          skus=[Sku(spec="标准", price_cents=8000, stock=2)])
        db.add(product)
        db.commit()
        product_id, sku_id = product.id, product.skus[0].id
        def recalled(*args):
            db.get(Product, product_id).status = "off"
            db.commit()
            return {(product_id, sku_id)}
        monkeypatch.setattr("app.services.product_search.semantic_matches", recalled)
        token = set_actor(db, Actor(buyer.id, "customer", buyer.username, 1))
        try:
            answer = execute_tool("search_products", {"keyword": "模糊用途查询"})
            assert "即时变更测试" not in answer
            assert "没有找到" in answer
        finally:
            reset_actor(token)
