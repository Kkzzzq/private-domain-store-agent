from app.core.security import hash_password
from app.models.tables import Order, OrderItem, Product, Shop, Sku, User


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
        status="on",
        sort_order=1,
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
        status="on",
        sort_order=2,
        skus=[Sku(spec="单只", price_cents=3900, stock=15)],
    )
    candle = Product(
        shop_id=shop.id,
        name="大豆香薰蜡烛",
        category="香氛",
        description="雪松香。点燃后不支持无理由退货。",
        status="on",
        sort_order=3,
        skus=[Sku(spec="雪松", price_cents=4900, stock=0)],
    )
    box = Product(
        shop_id=shop.id,
        name="桌面收纳盒",
        category="家居",
        description="原木收纳盒，当前下架。",
        status="off",
        sort_order=4,
        skus=[Sku(spec="原木", price_cents=7900, stock=5)],
    )
    db.add_all([pillow, mug, candle, box])
    db.flush()

    white = next(sku for sku in pillow.skus if sku.spec == "米白")
    cedar = candle.skus[0]
    cup = mug.skus[0]
    db.add_all(
        [
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
    db.commit()
