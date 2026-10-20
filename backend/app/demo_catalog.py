from pathlib import Path

from sqlalchemy import select

from app.models.tables import Product, Section, SectionItem, Shop, ShopCategory, Sku


PHOTO_SOURCES = [
    ("6312237", "white-ceramic-mug-on-white-table", "KATRIN BOLOVTSOVA"),
    ("1809127", "close-up-photo-of-cup", "Andrea Piacquadio"),
    ("5824584", "decorative-wicker-basket-in-cozy-room", "Charlotte May"),
    ("16725450", "wicker-basket-hanging-on-a-wire", "abdellah photographie"),
    ("15758184", "close-up-of-soft-pillow", "Marek Hrnčiarik"),
    ("8762876", "stack-of-colorful-pillows-isolated-on-beige-background", "Ron Lach"),
    ("4554344", "blank-notebook-on-white-background", "Engin Akyurt"),
    ("6682959", "a-blank-notebook", "Tara Winstead"),
]

PRODUCTS = [
    ("日常简约饮水杯", "餐具", [("素白陶瓷款", "6312237", 4900), ("浅灰搪瓷款", "1809127", 5200)]),
    ("自然系编织收纳篮", "家居", [("落地带盖款", "5824584", 8900), ("悬挂款", "16725450", 6900)]),
    ("暖居布艺软垫", "家居", [("素白坐垫款", "15758184", 5900), ("暖色靠垫组合款", "8762876", 12900)]),
    ("慢生活记录本", "文具", [("横线款", "4554344", 2900), ("空白线圈款", "6682959", 3500)]),
]


def photo_url(photo_id):
    return f"/covers/catalog/pexels-{photo_id}.jpg"


def expand_cup_skus(db, shop_code):
    product = db.scalar(select(Product).join(Shop).where(Shop.share_code == shop_code, Product.name == "日常简约饮水杯"))
    if product is None:
        raise ValueError("请先添加日常简约饮水杯演示商品")
    existing = {item.spec for item in product.skus}
    count = 0
    for style, photo_id, pairs in [
        ("素白陶瓷款", "6312237", [(2, 8800, 9800), (4, 16800, 19600)]),
        ("浅灰搪瓷款", "1809127", [(2, 9400, 10400), (4, 18000, 20800)]),
    ]:
        for quantity, price, original in pairs:
            spec = f"{style} · {quantity}只装"
            if spec not in existing:
                product.skus.append(Sku(spec=spec, image_url=photo_url(photo_id), price_cents=price,
                                        market_price_cents=original, stock=12))
                count += 1
    note = "未标装数的规格为单只；组合装图片展示同款单只外观，装数以所选规格为准。"
    if note not in product.description:
        product.description += "\n" + note
    db.commit()
    return count


def add_demo_catalog(db, shop_code, web_root):
    shop = db.scalar(select(Shop).where(Shop.share_code == shop_code))
    if shop is None:
        raise ValueError("目标店铺不存在")
    for photo_id, _, _ in PHOTO_SOURCES:
        path = Path(web_root) / photo_url(photo_id).lstrip("/")
        if not path.is_file() or path.stat().st_size < 1024:
            raise ValueError(f"商品图片缺失：{path.name}")
    created = []
    for offset, (name, category, variants) in enumerate(PRODUCTS):
        if db.scalar(select(Product.id).where(Product.shop_id == shop.id, Product.name == name)):
            continue
        if not db.scalar(select(ShopCategory.id).where(ShopCategory.shop_id == shop.id, ShopCategory.name == category)):
            db.add(ShopCategory(shop_id=shop.id, name=category, sort_order=20 + offset))
            db.flush()
        product = Product(
            shop_id=shop.id, name=name, category=category,
            description="生活方式演示商品，各款式配有对应图片。图片来自 Pexels 授权素材，仅用于商城功能演示，非商家实拍；售价与库存均为演示数据，不代表真实销售承诺。",
            image_url=photo_url(variants[0][1]), status="on", sort_order=30 + offset,
            sales_count=0,
            skus=[Sku(spec=spec, image_url=photo_url(photo_id), price_cents=price, stock=12)
                  for spec, photo_id, price in variants],
        )
        db.add(product)
        db.flush()
        created.append(product)
    section = db.scalar(select(Section).where(Section.shop_id == shop.id, Section.title == "日常新物"))
    if section is None and created:
        section = Section(shop_id=shop.id, title="日常新物", subtitle="杯具、布艺与收纳，挑一件喜欢的", source="manual", sort_order=0)
        db.add(section)
        db.flush()
    if section:
        for offset, product in enumerate(created):
            db.add(SectionItem(section_id=section.id, product_id=product.id, sort_order=offset))
    db.commit()
    return len(created)
