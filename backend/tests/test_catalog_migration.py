"""旧库就地迁移后关联、数据和重复启动保持有效。"""
from sqlalchemy import create_engine, inspect, text


def test_legacy_catalog_migration_preserves_data_and_foreign_keys(monkeypatch):
    from app import main
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(128), status VARCHAR(16))")
        connection.exec_driver_sql("CREATE TABLE skus (id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), spec VARCHAR(64), UNIQUE(product_id, spec))")
        connection.exec_driver_sql("INSERT INTO products VALUES (7, 'legacy', 'draft')")
        connection.exec_driver_sql("INSERT INTO skus VALUES (9, 7, 'standard')")
    monkeypatch.setattr(main, "engine", engine)
    main._ensure_catalog_schema()
    main._ensure_catalog_schema()
    with engine.connect() as connection:
        product = connection.execute(text("SELECT id, name, status, spu_id, updated_at FROM products")).one()
        assert product[:3] == (7, "legacy", "draft")
        assert product.spu_id.startswith("SP") and product.updated_at
        assert connection.execute(text("SELECT id, spu_id, spec FROM skus")).one() == (9, 7, "standard")
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    foreign_keys = inspect(engine).get_foreign_keys("skus")
    assert foreign_keys[0]["constrained_columns"] == ["spu_id"]
    assert foreign_keys[0]["referred_table"] == "products"
    assert any(index["unique"] and index["column_names"] == ["spu_id"]
               for index in inspect(engine).get_indexes("products"))
    engine.dispose()
