"""给既有南枝小店追加可识别的演示业务数据。默认只预览，绝不清库。

从 backend 执行；--apply 必须同时提供当前数据库名称与店铺编号。
演示已支付/物流状态只用于产品展示，不调用支付或快递服务。
"""
import argparse
import json
import secrets
from datetime import timedelta
from sqlalchemy import select, func


BATCH = "nanzhi-demo-20261021"
PREFIX = "【演示】"


def seed(db, shop_id):
    from app.core.security import hash_password
    from app.models.tables import (Address, Banner, CartItem, Coupon, Order,
        OrderItem, Product, ProductTag, ProductTagLink, Review, Section, SectionItem, Shop,
        ShopCategory, Sku, SkuParameterProfile, Testimonial, User, UserCoupon, utcnow)
    from app.models.support import AfterSale, Conversation, Message, Shipment

    shop = db.get(Shop, shop_id)
    if not shop or shop.share_code != "nanzhi":
        raise ValueError("目标必须是既有 nanzhi 店铺")
    marker = db.scalar(select(User).where(User.username == BATCH + "-01"))
    if marker:
        product_count=db.scalar(select(func.count()).select_from(Product).where(Product.shop_id==shop.id,Product.description.contains(BATCH)))
        order_count=db.scalar(select(func.count()).select_from(Order).where(Order.shop_id==shop.id,Order.order_no.startswith("NZDEMO20261021")))
        if product_count != 8 or order_count != 12:
            raise ValueError("演示批次不完整，停止追加以免重复；请先检查历史批次")
        return {"already_seeded": True, "batch": BATCH, "shop_id": shop.id}
    now = utcnow()
    users = []
    for index in range(6):
        user = User(username=f"{BATCH}-{index+1:02}", nickname=f"演示买家{index+1}",
                    password_hash=hash_password(secrets.token_urlsafe(32)), role="customer")
        db.add(user);db.flush();users.append(user)
        db.add(Address(user_id=user.id, receiver=f"演示收件人{index+1}", phone="00000000000",
                       region="演示省 演示市 演示区", detail="演示数据，请勿实际配送", is_default=True))
    categories = ["演示家居", "演示茶器", "演示香氛"]
    for name in categories:
        if not db.scalar(select(ShopCategory).where(ShopCategory.shop_id == shop.id, ShopCategory.name == name)):
            db.add(ShopCategory(shop_id=shop.id, name=name, sort_order=90))
    tags = []
    for name, color in [("演示新品", "#52745c"), ("演示低库存", "#ab6843")]:
        tag = db.scalar(select(ProductTag).where(ProductTag.shop_id == shop.id, ProductTag.name == name))
        if not tag:
            tag = ProductTag(shop_id=shop.id, name=name, color=color);db.add(tag);db.flush()
        tags.append(tag)
    image = db.scalar(select(Product.image_url).where(Product.shop_id == shop.id, Product.image_url != "").limit(1)) or ""
    products, skus = [], []
    for index, title in enumerate(["棉麻餐垫", "陶瓷茶杯", "木质托盘", "植物香薰", "旅行收纳袋", "玻璃花瓶", "新品试样", "季节限定套装"]):
        product = Product(shop_id=shop.id, name=PREFIX + title, category=categories[index % 3],
            description=f"演示业务数据，批次 {BATCH}；用于三端联调，非真实交易。", image_url=image,
            status="on" if index < 5 else "off" if index == 5 else "draft", sort_order=900 + index)
        db.add(product);db.flush();products.append(product)
        for variant, spec in enumerate(["米白 / 标准装", "浅绿 / 加大装", "限定礼盒"]):
            sku = Sku(product_id=product.id, spec=spec, price_cents=1900 + index*1000 + variant*500,
                market_price_cents=3900 + index*1000, stock=0 if index == 4 else 3 if index == 3 else 60,
                image_url=image, sort_order=variant, status="off" if variant == 2 else "on")
            db.add(sku);db.flush();skus.append(sku)
            db.add(SkuParameterProfile(sku_id=sku.id, parameters=[{"name":"数据用途", "value":"演示联调"}]))
        db.add(ProductTagLink(product_id=product.id, tag_id=tags[index % 2].id))
    coupons = []
    for name, start, end, enabled in [("新人满减", -1, 30, True), ("即将开始", 2, 10, True), ("已过期", -10, -1, True), ("已停用", -1, 30, False)]:
        coupon = Coupon(shop_id=shop.id, name=PREFIX+name, threshold_cents=1000, amount_cents=500,
            total_count=100, starts_at=now+timedelta(days=start), ends_at=now+timedelta(days=end), enabled=enabled)
        db.add(coupon);db.flush();coupons.append(coupon)
    statuses = ["pending", "paid", "shipped", "completed", "cancelled", "paid", "shipped", "completed", "paid", "completed", "shipped", "cancelled"]
    orders = []
    for index, status in enumerate(statuses):
        user = users[index % len(users)];sku = skus[(index % 3)*3];product = products[index % 3]
        order = Order(order_no=f"NZDEMO20261021{index+1:04}", shop_id=shop.id, user_id=user.id, status=status,
            total_cents=sku.price_cents, freight_cents=0, receiver=user.nickname, phone="00000000000",
            address="演示地址，请勿实际配送", created_at=now-timedelta(hours=index*6),
            expires_at=now+timedelta(minutes=30) if status == "pending" else None)
        db.add(order);db.flush();orders.append(order)
        item=OrderItem(order_id=order.id, product_id=product.id, sku_id=sku.id, product_name=product.name,
                       sku_spec=sku.spec, price_cents=sku.price_cents, quantity=1)
        db.add(item);db.flush()
        if status != "cancelled":sku.stock -= 1
        if status in ("paid", "shipped", "completed"):product.sales_count += 1
        if status in ("shipped", "completed"):
            db.add(Shipment(order_id=order.id, carrier="演示物流（未接快递）", tracking_number=f"DEMO-NZ-{index+1:06}",
                status="delivered" if status == "completed" else "shipped",
                events=[{"at":now.isoformat(), "role":"merchant", "description":"演示轨迹：商家维护，未调用真实物流"}]))
        if status == "completed":
            db.add(Review(user_id=user.id, product_id=product.id, order_item_id=item.id, rating=4+index%2,
                          content="演示评价：用于展示订单完成后的评价记录。"))
        if status in ("paid", "shipped") and index >= 5:
            db.add(AfterSale(order_id=order.id, kind="return" if index%2 else "exchange",
                reason="演示售后：尺码或颜色不合适，不执行资金退款", status=["requested","accepted","resolved"][index%3],
                events=[{"at":now.isoformat(), "role":"customer", "description":"演示售后申请"}]))
    for index,user in enumerate(users):
        coupon = UserCoupon(coupon_id=coupons[0].id, user_id=user.id, status="available")
        db.add(coupon);coupons[0].claimed_count += 1
        db.add(CartItem(user_id=user.id, shop_id=shop.id, sku_id=skus[0].id, quantity=index%3+1))
        conversation=Conversation(shop_id=shop.id, customer_id=user.id);db.add(conversation);db.flush()
        for role, sender, content in [("customer",user.id,"演示咨询：这款商品如何选规格？"),("merchant",shop.merchant_id,"演示回复：详情页可查看规格和库存，有问题随时联系。")]:
            db.add(Message(conversation_id=conversation.id, sender_id=sender, sender_role=role,
                           client_id=f"{BATCH}-{index}-{role}", content=content))
    section=Section(shop_id=shop.id, title=PREFIX+"联调商品", subtitle="演示专区", source="manual", sort_order=99)
    db.add(section);db.flush()
    for index,product in enumerate(products[:3]):db.add(SectionItem(section_id=section.id,product_id=product.id,sort_order=index))
    db.add(Banner(shop_id=shop.id,image_url=image,title=PREFIX+"南枝生活新品",subtitle="业务演示数据",link_type="product",link_value=str(products[0].id),sort_order=99))
    db.add(Testimonial(shop_id=shop.id,nickname="演示买家",content="演示内容：用于首页评价展示，不代表真实用户反馈。",sort_order=99))
    db.flush()
    return {"batch":BATCH,"shop_id":shop.id,"customers":len(users),"products":len(products),"skus":len(skus),
            "orders":len(orders),"order_statuses":sorted(set(statuses)),"coupons":len(coupons),
            "product_ids":[p.id for p in products],"user_ids":[u.id for u in users],"order_numbers":[o.order_no for o in orders]}


def main():
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.models.tables import Shop
    from sqlalchemy.engine import make_url
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--expected-database")
    parser.add_argument("--shop-id",type=int)
    args=parser.parse_args()
    database=make_url(settings.database_url).database
    with SessionLocal() as db:
        shop=db.scalar(select(Shop).where(Shop.share_code=="nanzhi"))
        if not shop:raise SystemExit("不存在 nanzhi 店铺，不会自动创建替代店铺")
        if not args.apply:
            print(json.dumps({"preview":True,"database":database,"shop_id":shop.id,"shop":shop.name,"batch":BATCH,"writes":False},ensure_ascii=False));return
        if args.expected_database != database or args.shop_id != shop.id:
            raise SystemExit("必须显式匹配目标数据库名称与店铺ID")
        target_shop_id=shop.id
        result=seed(db,target_shop_id);db.commit()
    from app.services.catalog import invalidate_catalog_cache
    invalidate_catalog_cache()
    print(json.dumps(result,ensure_ascii=False))


if __name__ == "__main__":main()
