from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.models.tables import Order, OrderItem, Product, Sku, User, utcnow
from app.schemas.dto import OrderCreate

FREE_SHIPPING_CENTS = 9900
BASE_FREIGHT_CENTS = 800
ORDER_TTL_MINUTES = 30
from app.services.catalog import invalidate_catalog_cache, load_sku_for_shop, merchant_shop, shop_by_code, yuan
from app.services.shelf import purchase_block

STATUS_LABELS = {
    "pending": "待支付",
    "paid": "已支付",
    "shipped": "已发货",
    "completed": "已完成",
    "cancelled": "已取消",
}


def serialize_order(order: Order, *, audience: str) -> dict:
    data = {
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
                "available": bool(item.product and item.product.status == "on" and order.shop and order.shop.status == "open"),
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
    return (
        f"订单 {data['order_no']}，{data['status_label']}，合计 ¥{data['total_yuan']:.2f}，"
        f"地址 {data['address']}。商品：{item_text}"
    )


def _orders():
    return select(Order).options(joinedload(Order.items), joinedload(Order.shop), joinedload(Order.buyer))


def _expires_in(order: Order) -> int | None:
    if order.status != "pending" or order.expires_at is None:
        return None
    return max(0, int((order.expires_at - utcnow()).total_seconds()))


def _next_order_no(db: Session) -> str:
    prefix = "PS" + datetime.now().strftime("%Y%m%d")
    count = db.query(Order).filter(Order.order_no.like(prefix + "%")).count() + 1
    return f"{prefix}{count:04d}"


def freight_for(goods_cents: int) -> int:
    if goods_cents <= 0 or goods_cents >= FREE_SHIPPING_CENTS:
        return 0
    return BASE_FREIGHT_CENTS


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
    return int(
        db.scalar(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.user_id == user_id,
                OrderItem.product_id == product_id,
                Order.status != "cancelled",
            )
        )
        or 0
    )


def create_order(db: Session, user: User, share_code: str, body: OrderCreate) -> dict:
    if user.role != "customer":
        raise HTTPException(status_code=403, detail="请使用买家账号下单")
    shop = shop_by_code(db, share_code)
    chosen: list[tuple[Sku, int]] = []
    limit_hit: dict[int, int] = {}
    for sku_id, quantity in _order_lines(body):
        sku = load_sku_for_shop(db, shop.id, sku_id)
        if sku is None:
            raise HTTPException(status_code=400, detail="没有找到这个商品")
        reason = purchase_block(sku, quantity)
        if reason:
            raise HTTPException(status_code=400, detail=reason)
        limit = sku.product.limit_per_user
        if limit:
            already = _bought_quantity(db, user.id, sku.product_id)
            if already + quantity > limit:
                limit_hit[sku.product_id] = limit
                continue
        chosen.append((sku, quantity))
    if limit_hit:
        name = next(
            (sku.product.name for sku, _ in chosen if sku.product_id in limit_hit),
            "部分商品",
        )
        limit = next(iter(limit_hit.values()))
        raise HTTPException(status_code=400, detail=f"{name} 每人限购 {limit} 件，已经买满了")
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
    order.freight_cents = freight_for(goods_cents)
    order.total_cents = goods_cents + order.freight_cents
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
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="这个订单不需要支付")
    order.status = "paid"
    order.expires_at = None
    for item in order.items:
        product = db.get(Product, item.product_id)
        if product is not None:
            product.sales_count += item.quantity
    db.commit()
    invalidate_catalog_cache()
    saved = db.scalars(_orders().where(Order.id == order.id)).unique().one()
    return serialize_order(saved, audience="c")


def _restore_stock(db: Session, order: Order) -> None:
    for item in order.items:
        sku = db.get(Sku, item.sku_id)
        if sku is not None:
            sku.stock += item.quantity


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
    for order in expired:
        _restore_stock(db, order)
        order.status = "cancelled"
        order.expires_at = None
    if expired:
        db.commit()
        invalidate_catalog_cache()
    return len(expired)


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
