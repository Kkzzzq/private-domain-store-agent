from sqlalchemy import select

from app.core.security import hash_password
from app.models.tables import Address, Order, OrderItem, Product, Review, Shop, Sku, User

COVERS = {
    "亚麻抱枕套": "/covers/pillow.svg",
    "陶瓷马克杯": "/covers/mug.svg",
    "大豆香薰蜡烛": "/covers/candle.svg",
    "桌面收纳盒": "/covers/box.svg",
    "亚麻桌旗": "/covers/runner.svg",
    "手作餐盘": "/covers/plate.svg",
    "无火扩香石": "/covers/stone.svg",
    "棉麻笔记本": "/covers/notebook.svg",
    "刺绣姓名贴": "/covers/patch.svg",
}


def seed_if_empty(db) -> None:
    if db.query(User).count() > 0:
        return
    merchant = User(
        username="merchant",
        password_hash=hash_password("merchant123"),
        role="merchant",
        nickname="南枝",
    )
    alice = User(
        username="alice",
        password_hash=hash_password("alice123"),
        role="customer",
        nickname="小满",
    )
    bob = User(
        username="bob",
        password_hash=hash_password("bob123"),
        role="customer",
        nickname="阿禾",
    )
    db.add_all([merchant, alice, bob])
    db.flush()

    shop = Shop(
        merchant_id=merchant.id,
        name="南枝手作",
        notice="这是商家分享的独立店铺。满 99 元包邮，定制品不支持无理由退货。",
        logo_url="/covers/shop.svg",
        theme_color="#ff5000",
        share_code="nanzhi",
        status="open",
    )
    db.add(shop)
    db.flush()

    pillow = Product(
        shop_id=shop.id,
        name="亚麻抱枕套",
        category="家居",
        description="可拆洗的亚麻抱枕套，冷水轻柔洗涤。",
        image_url="/covers/pillow.svg",
        status="on",
        sort_order=1,
        sales_count=26,
        skus=[
            Sku(spec="米白", price_cents=5900, stock=20),
            Sku(spec="雾蓝", price_cents=5900, stock=8),
        ],
    )
    mug = Product(
        shop_id=shop.id,
        name="陶瓷马克杯",
        category="餐具",
        description="日用陶瓷杯，可放洗碗机上层。",
        image_url="/covers/mug.svg",
        status="on",
        sort_order=2,
        sales_count=18,
        skus=[Sku(spec="单只", price_cents=3900, stock=15)],
    )
    candle = Product(
        shop_id=shop.id,
        name="大豆香薰蜡烛",
        category="香氛",
        description="雪松香。点燃后不支持无理由退货。",
        image_url="/covers/candle.svg",
        status="on",
        sort_order=3,
        sales_count=11,
        skus=[Sku(spec="雪松", price_cents=4900, stock=0)],
    )
    box = Product(
        shop_id=shop.id,
        name="桌面收纳盒",
        category="家居",
        description="原木收纳盒，当前下架。",
        image_url="/covers/box.svg",
        status="off",
        sort_order=4,
        skus=[Sku(spec="原木", price_cents=7900, stock=5)],
    )
    runner = Product(
        shop_id=shop.id,
        name="亚麻桌旗",
        category="家居",
        description="餐桌中间的一条亚麻桌旗，可机洗。",
        image_url="/covers/runner.svg",
        status="on",
        sort_order=5,
        sales_count=9,
        skus=[Sku(spec="米白 140cm", price_cents=8900, stock=12), Sku(spec="雾蓝 180cm", price_cents=10900, stock=6)],
    )
    plate = Product(
        shop_id=shop.id,
        name="手作餐盘",
        category="餐具",
        description="不规则釉面餐盘，适合日常早餐。",
        image_url="/covers/plate.svg",
        status="on",
        sort_order=6,
        sales_count=7,
        skus=[Sku(spec="暖白", price_cents=6900, stock=10)],
    )
    stone = Product(
        shop_id=shop.id,
        name="无火扩香石",
        category="香氛",
        description="石膏扩香石，滴上香薰油即可。",
        image_url="/covers/stone.svg",
        status="on",
        sort_order=7,
        sales_count=4,
        skus=[Sku(spec="圆石", price_cents=4500, stock=16)],
    )
    notebook = Product(
        shop_id=shop.id,
        name="棉麻笔记本",
        category="文具",
        description="裸背线装，内页无酸纸。",
        image_url="/covers/notebook.svg",
        status="on",
        sort_order=8,
        sales_count=15,
        limit_per_user=2,
        skus=[Sku(spec="A5 空白", price_cents=3200, stock=30), Sku(spec="A5 横线", price_cents=3200, stock=22)],
    )
    patch = Product(
        shop_id=shop.id,
        name="刺绣姓名贴",
        category="家居",
        description="定制品。禁售期间买家不可见。",
        image_url="/covers/patch.svg",
        status="banned",
        sort_order=9,
        skus=[Sku(spec="单枚", price_cents=1900, stock=40)],
    )
    db.add_all([pillow, mug, candle, box, runner, plate, stone, notebook, patch])
    db.flush()
    db.add(
        Address(
            user_id=alice.id,
            receiver="小满",
            phone="13800001111",
            region="湖南省长沙市岳麓区",
            detail="示范路 1 号",
            is_default=True,
        )
    )

    white = next(sku for sku in pillow.skus if sku.spec == "米白")
    cedar = candle.skus[0]
    cup = mug.skus[0]
    plate_sku = plate.skus[0]
    done_item = OrderItem(
        product_id=plate.id,
        sku_id=plate_sku.id,
        product_name=plate.name,
        sku_spec=plate_sku.spec,
        price_cents=plate_sku.price_cents,
        quantity=1,
    )
    db.add_all(
        [
            Order(
                order_no="PS202601100001",
                shop_id=shop.id,
                user_id=alice.id,
                status="completed",
                total_cents=6900,
                address="长沙市岳麓区示范路 1 号",
                items=[done_item],
            ),
            Order(
                order_no="PS202601150001",
                shop_id=shop.id,
                user_id=alice.id,
                status="paid",
                total_cents=5900,
                address="长沙市岳麓区示范路 1 号",
                items=[
                    OrderItem(
                        product_id=pillow.id,
                        sku_id=white.id,
                        product_name=pillow.name,
                        sku_spec=white.spec,
                        price_cents=white.price_cents,
                        quantity=1,
                    )
                ],
            ),
            Order(
                order_no="PS202601180002",
                shop_id=shop.id,
                user_id=alice.id,
                status="shipped",
                total_cents=4900,
                address="长沙市岳麓区示范路 1 号",
                items=[
                    OrderItem(
                        product_id=candle.id,
                        sku_id=cedar.id,
                        product_name=candle.name,
                        sku_spec=cedar.spec,
                        price_cents=cedar.price_cents,
                        quantity=1,
                    )
                ],
            ),
            Order(
                order_no="PS202601200001",
                shop_id=shop.id,
                user_id=bob.id,
                status="paid",
                total_cents=3900,
                address="益阳市赫山区示范街 8 号",
                items=[
                    OrderItem(
                        product_id=mug.id,
                        sku_id=cup.id,
                        product_name=mug.name,
                        sku_spec=cup.spec,
                        price_cents=cup.price_cents,
                        quantity=1,
                    )
                ],
            ),
        ]
    )
    db.flush()
    db.add(
        Review(
            user_id=alice.id,
            product_id=plate.id,
            order_item_id=done_item.id,
            rating=5,
            content="釉面很好看，早餐摆盘很上镜。",
        )
    )
    db.commit()


def upgrade_demo(db) -> None:
    """旧库只有第一版商品时，补上后来的规格、封面和默认地址。"""
    shop = db.scalar(select(Shop).where(Shop.share_code == "nanzhi"))
    if shop is None:
        return
    products = db.scalars(select(Product).where(Product.shop_id == shop.id)).all()
    by_name = {product.name: product for product in products}
    for name, url in COVERS.items():
        product = by_name.get(name)
        if product is not None and not product.image_url:
            product.image_url = url
    if "棉麻笔记本" not in by_name:
        db.add_all(
            [
                Product(
                    shop_id=shop.id,
                    name="亚麻桌旗",
                    category="家居",
                    description="餐桌中间的一条亚麻桌旗，可机洗。",
                    image_url=COVERS["亚麻桌旗"],
                    status="on",
                    sort_order=5,
                    sales_count=9,
                    skus=[Sku(spec="米白 140cm", price_cents=8900, stock=12), Sku(spec="雾蓝 180cm", price_cents=10900, stock=6)],
                ),
                Product(
                    shop_id=shop.id,
                    name="手作餐盘",
                    category="餐具",
                    description="不规则釉面餐盘，适合日常早餐。",
                    image_url=COVERS["手作餐盘"],
                    status="on",
                    sort_order=6,
                    sales_count=7,
                    skus=[Sku(spec="暖白", price_cents=6900, stock=10)],
                ),
                Product(
                    shop_id=shop.id,
                    name="无火扩香石",
                    category="香氛",
                    description="石膏扩香石，滴上香薰油即可。",
                    image_url=COVERS["无火扩香石"],
                    status="on",
                    sort_order=7,
                    sales_count=4,
                    skus=[Sku(spec="圆石", price_cents=4500, stock=16)],
                ),
                Product(
                    shop_id=shop.id,
                    name="棉麻笔记本",
                    category="文具",
                    description="裸背线装，内页无酸纸。",
                    image_url=COVERS["棉麻笔记本"],
                    status="on",
                    sort_order=8,
                    sales_count=15,
                    limit_per_user=2,
                    skus=[Sku(spec="A5 空白", price_cents=3200, stock=30), Sku(spec="A5 横线", price_cents=3200, stock=22)],
                ),
                Product(
                    shop_id=shop.id,
                    name="刺绣姓名贴",
                    category="家居",
                    description="定制品。禁售期间买家不可见。",
                    image_url=COVERS["刺绣姓名贴"],
                    status="banned",
                    sort_order=9,
                    skus=[Sku(spec="单枚", price_cents=1900, stock=40)],
                ),
            ]
        )
    if shop.logo_url is None:
        shop.logo_url = ""
    if not shop.theme_color:
        shop.theme_color = "#ff5000"
    alice = db.scalar(select(User).where(User.username == "alice"))
    if alice is not None and db.scalar(select(Address).where(Address.user_id == alice.id)) is None:
        db.add(
            Address(
                user_id=alice.id,
                receiver="小满",
                phone="13800001111",
                region="湖南省长沙市岳麓区",
                detail="示范路 1 号",
                is_default=True,
            )
        )
    db.commit()
