from datetime import datetime, timedelta, timezone
from secrets import randbelow

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.models.tables import Order, OrderItem, Product, Sku, User, utcnow
from app.schemas.dto import OrderCreate

FREE_SHIPPING_CENTS = 9900
BASE_FREIGHT_CENTS = 800
ORDER_TTL_MINUTES = 30
from app.services.catalog import invalidate_catalog_cache, load_sku_for_shop, merchant_shop, shop_by_code, yuan
from app.services.shelf import purchase_block, listed_on_c
from app.services.governance import shop_blocked
from app.services import coupons
from app.models.tables import CouponOrder

STATUS_LABELS = {
    "pending": "待支付",
    "paid": "已支付",
    "shipped": "已发货",
    "completed": "已完成",
    "cancelled": "已取消",
}


def serialize_order(order: Order, *, audience: str) -> dict:
    from sqlalchemy.orm import object_session
    session = object_session(order)
    coupon = session.scalar(select(CouponOrder).where(CouponOrder.order_id == order.id)) if session else None
    data = {
        "discount_yuan": yuan(coupon.discount_cents) if coupon else 0,
        "coupon_name": coupon.name if coupon else "",
        "order_no": order.order_no,
        "shop_id": order.shop_id,
        "shop_name": order.shop.name if order.shop is not None else "",
        "status": order.status,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "goods_yuan": yuan(sum(item.price_cents * item.quantity for item in order.items)),
        "freight_yuan": yuan(order.freight_cents),
        "total_yuan": yuan(order.total_cents),
        "created_at": order.created_at.replace(tzinfo=timezone.utc).isoformat() if order.created_at else None,
        "receiver": order.receiver or "",
        "phone": order.phone or "",
        "address": order.address,
        "expires_in_seconds": _expires_in(order),
        "items": [
            {
                "product_id": item.product_id,
                "sku_id": item.sku_id,
                "product_name": item.product_name,
                "sku_spec": item.sku_spec,
                "price_yuan": yuan(item.price_cents),
                "quantity": item.quantity,
                "image_url": (item.sku.image_url if item.sku else "") or (item.product.image_url if item.product else "") or "",
                "available": bool(item.product and listed_on_c(item.product)),
            }
            for item in order.items
        ],
    }
    if audience == "b":
        data["buyer_nickname"] = order.buyer.nickname if order.buyer is not None else ""
        data["buyer_username"] = order.buyer.username if order.buyer is not None else ""
    return data


def format_order_text(order: Order) -> str:
    data = serialize_order(order, audience="c")
    item_text = "，".join(
        f"{item['product_name']} {item['sku_spec']} x{item['quantity']}" for item in data["items"]
    )
    from sqlalchemy.orm import object_session
    from app.models.support import Shipment
    db = object_session(order)
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id)) if db else None
    logistics = f"。商家物流记录：{shipment.carrier}，运单号 {shipment.tracking_number}，状态 {shipment.status}" if shipment else "。暂无商家填写的物流记录，不可推测快递位置"
    return (
        f"订单 {data['order_no']}，{data['status_label']}，合计 ¥{data['total_yuan']:.2f}，"
        f"地址 {data['address']}。商品：{item_text}{logistics}"
    )


def _orders():
    return select(Order).options(joinedload(Order.items), joinedload(Order.shop), joinedload(Order.buyer))


def _expires_in(order: Order) -> int | None:
    if order.status != "pending" or order.expires_at is None:
        return None
    return max(0, int((order.expires_at - utcnow()).total_seconds()))


def _next_order_no(db: Session) -> str:
    # Count-based numbers collide when two requests arrive before either commits.
    # Keep the existing numeric format used by the order assistant and 32-char column.
    return "PS" + datetime.now().strftime("%Y%m%d") + f"{randbelow(10 ** 22):022d}"



def freight_for(goods_cents: int, shop=None) -> int:
    from app.services.storefront import storefront_settings
    settings = storefront_settings(shop) if shop is not None else None
    threshold = int(round(settings.free_shipping_yuan * 100)) if settings else FREE_SHIPPING_CENTS
    freight = int(round(settings.base_freight_yuan * 100)) if settings else BASE_FREIGHT_CENTS
    if goods_cents <= 0 or goods_cents >= threshold:
        return 0
    return freight


def _order_lines(body: OrderCreate) -> list[tuple[int, int]]:
    raw = [(item.sku_id, item.quantity) for item in body.items] if body.items else [(body.sku_id or 0, body.quantity)]
    merged: dict[int, int] = {}
    for sku_id, quantity in raw:
        merged[sku_id] = min(20, merged.get(sku_id, 0) + quantity)
    return list(merged.items())


def _reserve_stock(db: Session, sku_id: int, quantity: int) -> bool:
    """条件扣减，库存不够时影响 0 行。避免两个请求同时读到够用。"""
    result = db.execute(
        update(Sku).where(Sku.id == sku_id, Sku.stock >= quantity).values(stock=Sku.stock - quantity)
    )
    return result.rowcount == 1


def _bought_quantity(db: Session, user_id: int, product_id: int) -> int:
    # A locking read sees current committed orders even under MySQL REPEATABLE READ.
    quantities = db.scalars(select(OrderItem.quantity).join(Order, Order.id == OrderItem.order_id).where(
        Order.user_id == user_id, OrderItem.product_id == product_id,
        Order.status != "cancelled",
    ).with_for_update()).all()
    return sum(quantities)



def create_order(db: Session, user: User, share_code: str, body: OrderCreate) -> dict:
    if user.actor_role != "customer":
        raise HTTPException(status_code=403, detail="请使用买家账号下单")
    # Serialize this buyer's check-and-create sequence, including different SKU requests.
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    shop = shop_by_code(db, share_code)
    chosen: list[tuple[Sku, int]] = []
    product_quantities: dict[int, int] = {}
    for sku_id, quantity in _order_lines(body):
        sku = load_sku_for_shop(db, shop.id, sku_id)
        if sku is None:
            raise HTTPException(status_code=400, detail="没有找到这个商品")
        reason = purchase_block(sku, quantity)
        if reason:
            raise HTTPException(status_code=400, detail=reason)
        product_quantities[sku.product_id] = product_quantities.get(sku.product_id, 0) + quantity
        chosen.append((sku, quantity))
    checked = set()
    for sku, _ in chosen:
        if sku.product_id in checked:
            continue
        checked.add(sku.product_id)
        limit = sku.product.limit_per_user
        if limit and _bought_quantity(db, user.id, sku.product_id) + product_quantities[sku.product_id] > limit:
            raise HTTPException(status_code=400, detail=f"{sku.product.name} 每人限购 {limit} 件，已经买满了")
    if not chosen:
        raise HTTPException(status_code=400, detail="没有可下单的商品")
    goods_cents = 0
    order = Order(
        order_no=_next_order_no(db),
        shop_id=shop.id,
        user_id=user.id,
        status="pending",
        total_cents=0,
        freight_cents=0,
        receiver=body.receiver.strip(),
        phone=body.phone.strip(),
        address=body.address.strip(),
        expires_at=utcnow() + timedelta(minutes=ORDER_TTL_MINUTES),
    )
    for sku, quantity in chosen:
        if not _reserve_stock(db, sku.id, quantity):
            db.rollback()
            raise HTTPException(status_code=400, detail=f"{sku.product.name} 库存不足")
        goods_cents += sku.price_cents * quantity
        order.items.append(
            OrderItem(
                product_id=sku.product_id,
                sku_id=sku.id,
                product_name=sku.product.name,
                sku_spec=sku.spec,
                price_cents=sku.price_cents,
                quantity=quantity,
            )
        )
    order.freight_cents = freight_for(goods_cents, shop)
    try:
        discount = coupons.reserve(db, user.id, shop.id, body.user_coupon_id, goods_cents, order)
    except HTTPException:
        db.rollback()
        raise
    order.total_cents = goods_cents + order.freight_cents - discount
    db.add(order)
    db.commit()
    invalidate_catalog_cache()
    saved = db.scalars(_orders().where(Order.id == order.id)).unique().one()
    return serialize_order(saved, audience="c")


def list_b_orders(db: Session, user: User, status: str = "") -> list[dict]:
    shop = merchant_shop(db, user)
    query = _orders().where(Order.shop_id == shop.id).order_by(Order.id.desc())
    if status:
        query = query.where(Order.status == status)
    orders = db.scalars(query).unique().all()
    return [serialize_order(order, audience="b") for order in orders]


def list_c_orders(db: Session, user: User, share_code: str | None, status: str = "") -> list[dict]:
    query = _orders().where(Order.user_id == user.id).order_by(Order.id.desc())
    if share_code:
        shop = shop_by_code(db, share_code)
        query = query.where(Order.shop_id == shop.id)
    if status:
        query = query.where(Order.status == status)
    orders = db.scalars(query).unique().all()
    return [serialize_order(order, audience="c") for order in orders]


def pay_order(db: Session, user: User, order_no: str) -> dict:
    order = db.scalars(_orders().where(Order.order_no == order_no, Order.user_id == user.id)).unique().one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="没有找到这个订单")
    if shop_blocked(order.shop):
        raise HTTPException(403, "店铺被平台限制营业，暂不能支付")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="这个订单不需要支付")
    changed = db.execute(update(Order).where(Order.id == order.id, Order.status == "pending",
        (Order.expires_at.is_(None) | (Order.expires_at > utcnow()))).values(status="paid"))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, "订单已过期或状态已变更")
    coupons.transition(db, order, used=True)
    order.status = "paid"
    order.expires_at = None
    for item in order.items:
        db.execute(update(Product).where(Product.id == item.product_id)
            .values(sales_count=Product.sales_count + item.quantity))
    db.commit()
    invalidate_catalog_cache()
    saved = db.scalars(_orders().where(Order.id == order.id)).unique().one()
    return serialize_order(saved, audience="c")


def _restore_stock(db: Session, order: Order) -> None:
    for item in order.items:
        db.execute(update(Sku).where(Sku.id == item.sku_id)
            .values(stock=Sku.stock + item.quantity))


def ship_order(db: Session, user: User, order_no: str) -> dict:
    shop = merchant_shop(db, user)
    order = db.scalars(_orders().where(Order.order_no == order_no, Order.shop_id == shop.id)).unique().one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="没有找到这个订单")
    if order.status != "paid":
        raise HTTPException(status_code=400, detail="只有已支付的订单可以发货")
    order.status = "shipped"
    db.commit()
    saved = db.scalars(_orders().where(Order.id == order.id)).unique().one()
    return serialize_order(saved, audience="b")


def ship_orders(db: Session, user: User, order_nos: list[str]) -> dict:
    """批量发货。单个失败不影响其他，最后一起汇报。"""
    shop = merchant_shop(db, user)
    shipped: list[str] = []
    skipped: list[dict] = []
    for order_no in dict.fromkeys(order_nos):
        order = db.scalars(_orders().where(Order.order_no == order_no, Order.shop_id == shop.id)).unique().one_or_none()
        if order is None:
            skipped.append({"order_no": order_no, "reason": "没有找到这个订单"})
            continue
        if order.status != "paid":
            skipped.append({"order_no": order_no, "reason": f"当前是{STATUS_LABELS.get(order.status, order.status)}"})
            continue
        order.status = "shipped"
        shipped.append(order_no)
    db.commit()
    return {"shipped": shipped, "skipped": skipped}


def cancel_order(db: Session, user: User, order_no: str) -> dict:
    order = db.scalars(_orders().where(Order.order_no == order_no, Order.user_id == user.id)).unique().one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="没有找到这个订单")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="只有待支付订单可以取消")
    changed = db.execute(update(Order).where(Order.id == order.id, Order.status == "pending").values(status="cancelled"))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, "订单状态已变更")
    coupons.transition(db, order)
    _restore_stock(db, order)
    order.status = "cancelled"
    order.expires_at = None
    db.commit()
    invalidate_catalog_cache()
    saved = db.scalars(_orders().where(Order.id == order.id)).unique().one()
    return serialize_order(saved, audience="c")


def auto_cancel_expired(db: Session, now: datetime | None = None) -> int:
    """超时未支付的订单自动取消并退回库存。定时任务调用。"""
    moment = now or utcnow()
    expired = db.scalars(
        _orders().where(Order.status == "pending", Order.expires_at.is_not(None), Order.expires_at <= moment)
    ).unique().all()
    count = 0
    for order in expired:
        changed = db.execute(update(Order).where(Order.id == order.id, Order.status == "pending").values(status="cancelled"))
        if changed.rowcount != 1:
            continue
        count += 1
        coupons.transition(db, order)
        _restore_stock(db, order)
        order.status = "cancelled"
        order.expires_at = None
    if expired:
        db.commit()
        invalidate_catalog_cache()
    return count


def confirm_order(db: Session, user: User, order_no: str) -> dict:
    order = db.scalars(_orders().where(Order.order_no == order_no, Order.user_id == user.id)).unique().one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="没有找到这个订单")
    if order.status != "shipped":
        raise HTTPException(status_code=400, detail="只有已发货的订单可以确认收货")
    order.status = "completed"
    db.commit()
    saved = db.scalars(_orders().where(Order.id == order.id)).unique().one()
    return serialize_order(saved, audience="c")


def describe_my_orders(db: Session, user_id: int, shop_id: int, order_no: str | None = None) -> str:
    """订单不存在、不属于这家店、不属于当前用户时，返回同一句话。"""
    if order_no:
        order = db.scalars(
            _orders().where(Order.order_no == order_no, Order.user_id == user_id, Order.shop_id == shop_id)
        ).unique().one_or_none()
        if order is None:
            return "没有找到这个订单。"
        return format_order_text(order)
    orders = db.scalars(
        _orders().where(Order.user_id == user_id, Order.shop_id == shop_id).order_by(Order.id.desc()).limit(5)
    ).unique().all()
    if not orders:
        return "你还没有订单。"
    return "\n".join(format_order_text(order) for order in orders)
