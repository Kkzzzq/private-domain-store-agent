from sqlalchemy import select

from app.core.security import hash_password
from app.models.tables import (
    Address,
    Banner,
    Order,
    OrderItem,
    Product,
    Review,
    Section,
    SectionItem,
    Shop,
    Sku,
    Testimonial,
    User,
)

# 商品图用 Unsplash 的免费照片，已下载到 web/covers
COVERS = {
    "亚麻抱枕套": "/covers/pillow.jpg",
    "陶瓷马克杯": "/covers/mug.jpg",
    "大豆香薰蜡烛": "/covers/candle.jpg",
    "桌面收纳盒": "/covers/box.jpg",
    "亚麻桌旗": "/covers/runner.jpg",
    "手作餐盘": "/covers/plate.jpg",
    "无火扩香石": "/covers/diffuser.jpg",
    "棉麻笔记本": "/covers/notebook.jpg",
    "刺绣姓名贴": "/covers/patch.jpg",
}

# 划线价按规格写死，只用来展示折扣，实付仍是 price_cents
MARKET_PRICE = {
    "米白": 8900,
    "雾蓝": 8900,
    "单只": 5900,
    "雪松": 7900,
    "原木": 11900,
    "米白 140cm": 12900,
    "雾蓝 180cm": 15900,
    "暖白": 9900,
    "圆石": 6900,
    "A5 空白": 4900,
    "A5 横线": 4900,
    "单枚": 2900,
}


def sku(spec: str, price_cents: int, stock: int) -> Sku:
    return Sku(
        spec=spec,
        price_cents=price_cents,
        market_price_cents=MARKET_PRICE.get(spec, 0),
        stock=stock,
    )


# 再补一批，让"全部商品"够三行以上，能演示展开
EXTRA = [
    ("亚麻餐垫", "家居", "双面亚麻餐垫，四片一组。桌布上再垫一层，汤水洒了也好收拾。", "/covers/runner.jpg", 3800, 24),
    ("藤编收纳篮", "家居", "手工藤编，可以放在玄关装钥匙和口罩，也能当果盘。", "/covers/box.jpg", 12800, 9),
    ("手工冷制皂", "香氛", "橄榄油配方，晾足了六周才出货，泡沫细，洗后不干。", "/covers/diffuser.jpg", 4200, 30),
    ("木质早餐托盘", "餐具", "整块白蜡木开出来，边缘做了圆角，端到床上也稳。", "/covers/plate.jpg", 15800, 6),
    ("陶瓷小花器", "家居", "瓶口收得很窄，一枝花也能站住，适合插窗外折回来的那枝。", "/covers/mug.jpg", 8800, 12),
    ("棉麻窗帘绑带", "家居", "一对装，磁吸扣，不用打孔，米白配浅色窗帘正好。", "/covers/pillow.jpg", 3600, 40),
    ("手作陶瓷茶碗", "餐具", "口径 9cm，一人一碗。釉面有细小的开片，用久了会更润。", "/covers/plate.jpg", 7800, 14),
    ("香薰蜡烛礼盒", "香氛", "两支装，雪松和无花果，配牛皮纸礼盒，可以直接送人。", "/covers/candle.jpg", 10800, 8),
    ("亚麻桌布", "家居", "水洗亚麻，铺上就有松弛感，可机洗。", "/covers/runner.jpg", 13800, 7),
    ("陶瓷调味罐", "餐具", "带木盖的一对，密封圈可以拆下来洗。", "/covers/mug.jpg", 6800, 18),
]


def add_extra_products(db, shop: Shop) -> None:
    for offset, (name, category, description, image, price, stock) in enumerate(EXTRA):
        db.add(
            Product(
                shop_id=shop.id,
                name=name,
                category=category,
                description=description,
                image_url=image,
                status="on",
                sort_order=10 + offset,
                sales_count=max(3, 40 - offset * 4),
                skus=[sku("标准", price, stock)],
            )
        )


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
        logo_url="",
        theme_color="#c9502f",
        share_code="nanzhi",
        status="open",
    )
    db.add(shop)
    db.flush()

    pillow = Product(
        shop_id=shop.id,
        name="亚麻抱枕套",
        category="家居",
        description="可拆洗的亚麻抱枕套，冷水轻柔洗涤，展开阴干即可。两个色号都是低饱和度的，配原木和藤编家具都合适。",
        image_url="/covers/pillow.jpg",
        status="on",
        sort_order=1,
        sales_count=126,
        skus=[sku("米白", 5900, 20), sku("雾蓝", 5900, 8)],
    )
    mug = Product(
        shop_id=shop.id,
        name="陶瓷马克杯",
        category="餐具",
        description="日用陶瓷杯，容量 320ml，可以放在洗碗机上层。杯壁偏厚，装热饮手感不烫。",
        image_url="/covers/mug.jpg",
        status="on",
        sort_order=2,
        sales_count=88,
        skus=[sku("单只", 3900, 15)],
    )
    candle = Product(
        shop_id=shop.id,
        name="大豆香薰蜡烛",
        category="香氛",
        description="雪松香。第一次点燃请烧到表面蜡油完全融化，避免只烧出一条坑。已经点燃的蜡烛不支持退货。",
        image_url="/covers/candle.jpg",
        status="on",
        sort_order=3,
        sales_count=41,
        skus=[sku("雪松", 4900, 0)],
    )
    box = Product(
        shop_id=shop.id,
        name="桌面收纳盒",
        category="家居",
        description="原木收纳盒，表面只上木蜡油。当前下架，补货后再上架。",
        image_url="/covers/box.jpg",
        status="off",
        sort_order=4,
        skus=[sku("原木", 7900, 5)],
    )
    runner = Product(
        shop_id=shop.id,
        name="亚麻桌旗",
        category="家居",
        description="餐桌中间的一条亚麻桌旗，可机洗。两条长度对应不同尺寸的餐桌，量一下再下单。",
        image_url="/covers/runner.jpg",
        status="on",
        sort_order=5,
        sales_count=63,
        skus=[sku("米白 140cm", 8900, 12), sku("雾蓝 180cm", 10900, 6)],
    )
    plate = Product(
        shop_id=shop.id,
        name="手作餐盘",
        category="餐具",
        description="不规则釉面餐盘，直径 21cm，适合日常早餐。每一只的釉色深浅都会有一点差别。",
        image_url="/covers/plate.jpg",
        status="on",
        sort_order=6,
        sales_count=57,
        skus=[sku("暖白", 6900, 10)],
    )
    stone = Product(
        shop_id=shop.id,
        name="无火扩香石",
        category="香氛",
        description="石膏扩香石，滴上香薰油即可，不用点火。放衣柜和玄关都合适。",
        image_url="/covers/diffuser.jpg",
        status="on",
        sort_order=7,
        sales_count=29,
        skus=[sku("圆石", 4500, 16)],
    )
    notebook = Product(
        shop_id=shop.id,
        name="棉麻笔记本",
        category="文具",
        description="裸背线装，可以完全摊平，内页无酸纸不洇墨。手作商品数量有限，每人限购两本。",
        image_url="/covers/notebook.jpg",
        status="on",
        sort_order=8,
        sales_count=74,
        limit_per_user=2,
        skus=[sku("A5 空白", 3200, 30), sku("A5 横线", 3200, 22)],
    )
    patch = Product(
        shop_id=shop.id,
        name="刺绣姓名贴",
        category="家居",
        description="手工刺绣的姓名贴，可以做校服和书包标记。属于定制品，审批通过前暂时禁售。",
        image_url="/covers/patch.jpg",
        status="banned",
        sort_order=9,
        skus=[sku("单枚", 1900, 40)],
    )
    # 先加主推的几件，让它们的 id 靠前，再加上补充的
    db.add_all([pillow, mug, candle, box, runner, plate, stone, notebook, patch])
    add_extra_products(db, shop)
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

    white = next(item for item in pillow.skus if item.spec == "米白")
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
                receiver="小满",
                phone="13800001111",
                items=[done_item],
            ),
            Order(
                order_no="PS202601150001",
                shop_id=shop.id,
                user_id=alice.id,
                status="paid",
                total_cents=5900,
                address="长沙市岳麓区示范路 1 号",
                receiver="小满",
                phone="13800001111",
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
                receiver="小满",
                phone="13800001111",
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
                receiver="阿禾",
                phone="13900002222",
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
            content="釉面很好看，早餐摆盘很上镜，边缘打磨得很光滑。",
        )
    )
    seed_home(db, shop, [pillow, mug, candle, runner, plate, stone, notebook])
    db.commit()


def seed_home(db, shop: Shop, products: list[Product]) -> None:
    """首页内容：三张轮播图、推荐位、畅销榜、一个自定义栏目和几条用户评价。"""
    by_name = {product.name: product for product in products}
    db.add_all(
        [
            Banner(
                shop_id=shop.id,
                image_url="/covers/hero.jpg",
                title=shop.name,
                subtitle="小批量手作，每个季度只做几批",
                link_type="none",
                sort_order=1,
            ),
            Banner(
                shop_id=shop.id,
                image_url="/covers/pillow.jpg",
                title="换季换一套床品",
                subtitle="亚麻抱枕套新到雾蓝，低饱和耐看",
                link_type="product",
                link_value=str(by_name["亚麻抱枕套"].id),
                sort_order=2,
            ),
            Banner(
                shop_id=shop.id,
                image_url="/covers/mug.jpg",
                title="早餐从一只杯子开始",
                subtitle="厚壁陶瓷，装热饮不烫手",
                link_type="product",
                link_value=str(by_name["陶瓷马克杯"].id),
                sort_order=3,
            ),
        ]
    )

    recommend = Section(
        shop_id=shop.id,
        title="店主推荐",
        subtitle="最近常被问到的几件",
        source="manual",
        sort_order=1,
    )
    best = Section(
        shop_id=shop.id,
        title="Best Seller 畅销榜",
        subtitle="按销量自动排序",
        source="sales",
        sort_order=2,
    )
    gift = Section(
        shop_id=shop.id,
        title="送人体面 · 伴手礼",
        subtitle="适合随手带一件的组合",
        source="manual",
        sort_order=3,
    )
    db.add_all([recommend, best, gift])
    db.flush()
    for index, name in enumerate(["亚麻抱枕套", "陶瓷马克杯", "手作餐盘", "亚麻桌旗", "棉麻笔记本", "无火扩香石"]):
        db.add(SectionItem(section_id=recommend.id, product_id=by_name[name].id, sort_order=index))
    for index, name in enumerate(["无火扩香石", "棉麻笔记本", "陶瓷马克杯", "大豆香薰蜡烛"]):
        db.add(SectionItem(section_id=gift.id, product_id=by_name[name].id, sort_order=index))

    db.add_all(
        [
            Testimonial(
                shop_id=shop.id,
                nickname="小满",
                content="抱枕套洗了两次没有缩水，米白配原木桌很好看。",
                rating=5,
                sort_order=1,
            ),
            Testimonial(
                shop_id=shop.id,
                nickname="阿禾",
                content="杯子比想象中厚实，早上泡茶放十分钟还是温的。",
                rating=5,
                sort_order=2,
            ),
            Testimonial(
                shop_id=shop.id,
                nickname="晚晚",
                content="桌旗的长度标注很准，按店家建议选的尺寸刚好。",
                rating=5,
                sort_order=3,
            ),
            Testimonial(
                shop_id=shop.id,
                nickname="老周",
                content="下单第二天就发了，包装是可回收的纸盒，没有多余塑料。",
                rating=4,
                sort_order=4,
            ),
            Testimonial(
                shop_id=shop.id,
                nickname="香菇",
                content="扩香石放在玄关，进门就有一点雪松味，很舒服。",
                rating=5,
                sort_order=5,
            ),
        ]
    )


def upgrade_demo(db) -> None:
    """旧库升级：补封面、补划线价、补默认地址，缺的商品也补齐。"""
    shop = db.scalar(select(Shop).where(Shop.share_code == "nanzhi"))
    if shop is None:
        return
    products = db.scalars(select(Product).where(Product.shop_id == shop.id)).all()
    by_name = {product.name: product for product in products}

    if shop.logo_url and shop.logo_url.endswith(".svg"):
        shop.logo_url = ""
    if not shop.theme_color:
        shop.theme_color = "#c9502f"

    for name, url in COVERS.items():
        product = by_name.get(name)
        if product is None:
            continue
        if not product.image_url or product.image_url.endswith(".svg"):
            product.image_url = url
        for item in product.skus:
            if not item.market_price_cents:
                item.market_price_cents = MARKET_PRICE.get(item.spec, 0)

    if "棉麻笔记本" not in by_name:
        db.add_all(
            [                Product(
                    shop_id=shop.id,
                    name="亚麻桌旗",
                    category="家居",
                    description="餐桌中间的一条亚麻桌旗，可机洗。",
                    image_url=COVERS["亚麻桌旗"],
                    status="on",
                    sort_order=5,
                    sales_count=63,
                    skus=[sku("米白 140cm", 8900, 12), sku("雾蓝 180cm", 10900, 6)],
                ),
                Product(
                    shop_id=shop.id,
                    name="手作餐盘",
                    category="餐具",
                    description="不规则釉面餐盘，适合日常早餐。",
                    image_url=COVERS["手作餐盘"],
                    status="on",
                    sort_order=6,
                    sales_count=57,
                    skus=[sku("暖白", 6900, 10)],
                ),
                Product(
                    shop_id=shop.id,
                    name="无火扩香石",
                    category="香氛",
                    description="石膏扩香石，滴上香薰油即可。",
                    image_url=COVERS["无火扩香石"],
                    status="on",
                    sort_order=7,
                    sales_count=29,
                    skus=[sku("圆石", 4500, 16)],
                ),
                Product(
                    shop_id=shop.id,
                    name="棉麻笔记本",
                    category="文具",
                    description="裸背线装，内页无酸纸。",
                    image_url=COVERS["棉麻笔记本"],
                    status="on",
                    sort_order=8,
                    sales_count=74,
                    limit_per_user=2,
                    skus=[sku("A5 空白", 3200, 30), sku("A5 横线", 3200, 22)],
                ),
                Product(
                    shop_id=shop.id,
                    name="刺绣姓名贴",
                    category="家居",
                    description="定制品。禁售期间买家不可见。",
                    image_url=COVERS["刺绣姓名贴"],
                    status="banned",
                    sort_order=9,
                    skus=[sku("单枚", 1900, 40)],
                ),
            ]
        )

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

    if db.scalar(select(Product).where(Product.shop_id == shop.id, Product.name == "亚麻餐垫")) is None:
        add_extra_products(db, shop)
    db.commit()

    if db.scalar(select(Banner).where(Banner.shop_id == shop.id)) is None:
        fresh = db.scalars(select(Product).where(Product.shop_id == shop.id)).all()
        seed_home(db, shop, fresh)
        db.commit()
