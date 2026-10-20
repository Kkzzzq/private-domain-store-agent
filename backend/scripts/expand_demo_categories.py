"""Add editable demo categories/products to a shop, without replacing existing data."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.tables import Product, Sku, Shop, ShopCategory, Section, SectionItem
from app.services.catalog import invalidate_catalog_cache


DEMO_ROWS = [
    ("香氛", "暖光香氛蜡烛", "candle.jpg", 5900, "标准装", "双份装"),
    ("香氛", "居室无火香薰", "diffuser.jpg", 7900, "单瓶装", "双瓶装"),
    ("收纳", "桌面杂物收纳盒", "box.jpg", 3900, "单件装", "两件装"),
    ("收纳", "编织置物篮", "catalog/pexels-5824584.jpg", 8900, "单件装", "两件装"),
    ("布艺", "自然色桌旗", "runner.jpg", 6900, "原色款", "蓝色款"),
    ("布艺", "柔软家居靠垫", "pillow.jpg", 4900, "素色款", "蓝色款"),
    ("杯具", "日用陶瓷马克杯", "mug.jpg", 4500, "单只装", "两只装"),
    ("杯具", "素白早餐杯", "catalog/pexels-6312237.jpg", 3900, "单只装", "两只装"),
    ("装饰", "花纹装饰盘", "plate.jpg", 5900, "单件装", "两件装"),
    ("装饰", "布艺装饰贴", "patch.jpg", 1900, "单件装", "两件装"),
    ("礼盒", "杯具分享套装", "mug.jpg", 8800, "两只装", "四只装"),
    ("礼盒", "手帐记录套装", "notebook.jpg", 5800, "两本装", "四本装"),
]


def expand(db, shop_code, web_root):
    shop = db.scalar(select(Shop).where(Shop.share_code == shop_code))
    if shop is None:
        raise ValueError("店铺不存在")
    for _, _, image, *_ in DEMO_ROWS:
        if not (Path(web_root) / "covers" / image).is_file():
            raise ValueError(f"图片缺失：{image}")
    section = db.scalar(select(Section).where(Section.shop_id == shop.id, Section.title == "日常新物"))
    if section is None:
        section = Section(shop_id=shop.id, title="日常新物", source="manual", sort_order=0)
        db.add(section)
        db.flush()
    category_order = db.scalar(select(func.max(ShopCategory.sort_order)).where(ShopCategory.shop_id == shop.id)) or 0
    item_order = db.scalar(select(func.max(SectionItem.sort_order)).where(SectionItem.section_id == section.id)) or 0
    created = 0
    for index, (category, name, image, price, first, second) in enumerate(DEMO_ROWS):
        if not db.scalar(select(ShopCategory.id).where(ShopCategory.shop_id == shop.id, ShopCategory.name == category)):
            category_order += 1
            db.add(ShopCategory(shop_id=shop.id, name=category, sort_order=category_order))
            db.flush()
        product = db.scalar(select(Product).where(Product.shop_id == shop.id, Product.name == name))
        if product is None:
            other_image = {"蓝色款": "pillow-blue.jpg" if "靠垫" in name else "runner-blue.jpg"}.get(second, image)
            product = Product(shop_id=shop.id, name=name, category=category, status="on",
                image_url=f"/covers/{image}", sort_order=100 + index, sales_count=0,
                description="店铺分类与交易流程演示商品。图片为已有演示素材；价格、库存及规格均为模拟数据，非真实销售承诺。组合装图片仅展示单件外观，数量以规格名称为准。",
                skus=[Sku(spec=first, image_url=f"/covers/{image}", price_cents=price, stock=24),
                      Sku(spec=second, image_url=f"/covers/{other_image}", price_cents=price if second == "蓝色款" else price * 2 - 500, stock=12)])
            db.add(product)
            db.flush()
            created += 1
        if not db.scalar(select(SectionItem.id).where(SectionItem.section_id == section.id, SectionItem.product_id == product.id)):
            item_order += 1
            db.add(SectionItem(section_id=section.id, product_id=product.id, sort_order=item_order))
    db.commit()
    invalidate_catalog_cache()
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shop", required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        print(f"新增 {expand(db, args.shop, Path(__file__).resolve().parents[2] / 'web')} 件演示商品")
