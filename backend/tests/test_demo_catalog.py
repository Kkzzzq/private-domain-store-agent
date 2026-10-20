import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.demo_catalog import PHOTO_SOURCES, PRODUCTS, add_demo_catalog, expand_cup_skus
from app.models.tables import Product, Section, SectionItem


def test_add_catalog_idempotent_and_distinct_sku_photos(client, tmp_path):
    directory = tmp_path / "covers" / "catalog"
    directory.mkdir(parents=True)
    for photo_id, _, _ in PHOTO_SOURCES:
        (directory / f"pexels-{photo_id}.jpg").write_bytes(b"image-fixture" * 100)
    with SessionLocal() as db:
        assert add_demo_catalog(db, "nanzhi", tmp_path) == 4
        products = db.scalars(select(Product).where(Product.name.in_([item[0] for item in PRODUCTS]))).all()
        assert len(products) == 4
        assert len({sku.image_url for product in products for sku in product.skus}) == 8
        assert all(len(product.skus) == 2 and product.sales_count == 0 for product in products)
        assert add_demo_catalog(db, "nanzhi", tmp_path) == 0
        section = db.scalar(select(Section).where(Section.title == "日常新物"))
        assert db.scalar(select(func.count()).select_from(SectionItem).where(SectionItem.section_id == section.id)) == 4


def test_missing_photos_prevents_catalog_write(client, tmp_path):
    with SessionLocal() as db:
        with pytest.raises(ValueError, match="商品图片缺失"):
            add_demo_catalog(db, "nanzhi", tmp_path)
        assert not db.scalar(select(Product.id).where(Product.name == PRODUCTS[0][0]))


def test_multi_sku_cup_expansion(client, tmp_path):
    directory = tmp_path / "covers" / "catalog"
    directory.mkdir(parents=True)
    for photo_id, _, _ in PHOTO_SOURCES:
        (directory / f"pexels-{photo_id}.jpg").write_bytes(b"image-fixture" * 100)
    with SessionLocal() as db:
        add_demo_catalog(db, "nanzhi", tmp_path)
        assert expand_cup_skus(db, "nanzhi") == 4
        assert expand_cup_skus(db, "nanzhi") == 0
        product = db.scalar(select(Product).where(Product.name == "日常简约饮水杯"))
        assert len(product.skus) == 6
        combos = [sku for sku in product.skus if "只装" in sku.spec]
        assert len(combos) == 4
        assert all(sku.image_url and sku.stock > 0 and sku.market_price_cents > sku.price_cents for sku in combos)
