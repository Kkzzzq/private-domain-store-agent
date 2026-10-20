"""Shop-wide fixed-amount coupons; all money and eligibility are server-owned."""
from datetime import datetime, timezone
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from app.models.tables import Coupon, UserCoupon, CouponOrder, utcnow
from app.schemas.dto import OrderLine
from app.services.catalog import merchant_shop, shop_by_code, load_sku_for_shop, yuan
from app.services.shelf import purchase_block


class CouponIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    threshold_cents: int = Field(ge=0, le=100000000)
    amount_cents: int = Field(ge=1, le=100000000)
    total_count: int = Field(ge=1, le=1000000)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def valid(self):
        self.name = self.name.strip()
        for key in ("starts_at", "ends_at"):
            value = getattr(self, key)
            if value.tzinfo:
                setattr(self, key, value.astimezone(timezone.utc).replace(tzinfo=None))
        if not self.name or self.ends_at <= self.starts_at or self.ends_at <= utcnow():
            raise ValueError("请填写名称及有效的起止时间")
        return self


class CouponStatus(BaseModel):
    enabled: bool


class CouponQuote(BaseModel):
    items: list[OrderLine] = Field(min_length=1, max_length=100)
    user_coupon_id: int | None = Field(default=None, ge=1)


def active(coupon):
    now = utcnow()
    return coupon.enabled and coupon.starts_at <= now < coupon.ends_at


def issuance_state(coupon):
    now = utcnow()
    if not coupon.enabled:
        return "disabled"
    if now < coupon.starts_at:
        return "scheduled"
    if now >= coupon.ends_at:
        return "expired"
    if coupon.claimed_count >= coupon.total_count:
        return "exhausted"
    return "active"


def payload(db, coupon, user_id=None):
    owned = db.scalar(select(UserCoupon).where(UserCoupon.coupon_id == coupon.id, UserCoupon.user_id == user_id)) if user_id else None
    counts = dict(db.execute(select(UserCoupon.status, func.count(UserCoupon.id)).where(
        UserCoupon.coupon_id == coupon.id).group_by(UserCoupon.status)).all())
    return dict(id=coupon.id, name=coupon.name, threshold_cents=coupon.threshold_cents,
        issuance_state=issuance_state(coupon), remaining_count=max(0, coupon.total_count - coupon.claimed_count),
        reserved_count=counts.get("reserved", 0), unused_count=counts.get("available", 0),
        amount_cents=coupon.amount_cents, total_count=coupon.total_count, claimed_count=coupon.claimed_count,
        starts_at=coupon.starts_at.replace(tzinfo=timezone.utc).isoformat(),
        ends_at=coupon.ends_at.replace(tzinfo=timezone.utc).isoformat(), enabled=coupon.enabled,
        active=active(coupon), user_coupon_id=owned.id if owned else None,
        status=owned.status if owned else "unclaimed",
        can_claim=active(coupon) and not owned and coupon.claimed_count < coupon.total_count,
        used_count=db.scalar(select(func.count()).select_from(CouponOrder).join(UserCoupon, UserCoupon.id == CouponOrder.user_coupon_id).where(UserCoupon.coupon_id == coupon.id, CouponOrder.status == "used")) or 0)


def list_b(db, user):
    shop = merchant_shop(db, user)
    return [payload(db, c) for c in db.scalars(select(Coupon).where(Coupon.shop_id == shop.id).order_by(Coupon.id.desc())).all()]


def create(db, user, body):
    shop = merchant_shop(db, user)
    row = Coupon(shop_id=shop.id, **body.model_dump())
    db.add(row)
    db.commit()
    return payload(db, row)


def toggle(db, user, coupon_id, body):
    shop = merchant_shop(db, user)
    result = db.execute(update(Coupon).where(Coupon.id == coupon_id, Coupon.shop_id == shop.id).values(enabled=body.enabled))
    if result.rowcount != 1:
        raise HTTPException(404, "没有找到这张优惠券")
    db.commit()
    return payload(db, db.get(Coupon, coupon_id))


def list_c(db, code, user=None):
    shop = shop_by_code(db, code)
    rows = db.scalars(select(Coupon).where(Coupon.shop_id == shop.id).order_by(Coupon.id.desc())).all()
    result = [payload(db, c, user.id if user else None) for c in rows]
    return [c for c in result if c["active"] or c["user_coupon_id"]]


def claim(db, user, code, coupon_id):
    shop = shop_by_code(db, code)
    now = utcnow()
    # Conditional update serializes issuance and cannot oversell the quota.
    result = db.execute(update(Coupon).where(Coupon.id == coupon_id, Coupon.shop_id == shop.id,
        Coupon.enabled.is_(True), Coupon.starts_at <= now, Coupon.ends_at > now,
        Coupon.claimed_count < Coupon.total_count).values(claimed_count=Coupon.claimed_count + 1))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(400, "优惠券尚未开始、已结束、停用或领完")
    try:
        db.add(UserCoupon(coupon_id=coupon_id, user_id=user.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "每人限领一张，你已经领取过了") from exc
    return payload(db, db.get(Coupon, coupon_id), user.id)


def validate(db, user_id, shop_id, user_coupon_id, goods_cents, lock=False):
    row = db.scalar(select(UserCoupon).where(UserCoupon.id == user_coupon_id, UserCoupon.user_id == user_id))
    coupon = db.get(Coupon, row.coupon_id) if row else None
    if not row or not coupon or coupon.shop_id != shop_id or row.status != "available":
        raise HTTPException(400, "优惠券不属于当前账号或店铺，或已被使用")
    if lock:
        now = utcnow()
        changed = db.execute(update(Coupon).where(Coupon.id == coupon.id, Coupon.enabled.is_(True),
            Coupon.starts_at <= now, Coupon.ends_at > now).values(claimed_count=Coupon.claimed_count))
        if changed.rowcount != 1:
            raise HTTPException(400, "优惠券已失效")
    if not active(coupon):
        raise HTTPException(400, "优惠券尚未开始、已过期或停用")
    if goods_cents < coupon.threshold_cents:
        raise HTTPException(400, "商品金额未达到优惠券门槛")
    return row, coupon, min(coupon.amount_cents, goods_cents)


def reserve(db, user_id, shop_id, user_coupon_id, goods_cents, order):
    if not user_coupon_id:
        return 0
    row, coupon, discount = validate(db, user_id, shop_id, user_coupon_id, goods_cents, lock=True)
    changed = db.execute(update(UserCoupon).where(UserCoupon.id == row.id, UserCoupon.status == "available").values(status="reserved"))
    if changed.rowcount != 1:
        raise HTTPException(409, "该优惠券正在另一笔订单中使用")
    db.add(order)
    db.flush()
    db.add(CouponOrder(order_id=order.id, user_coupon_id=row.id, name=coupon.name, discount_cents=discount))
    return discount


def transition(db, order, used=False):
    record = db.scalar(select(CouponOrder).where(CouponOrder.order_id == order.id))
    if not record:
        return
    changed = db.execute(update(CouponOrder).where(CouponOrder.id == record.id, CouponOrder.status == "reserved")
        .values(status="used" if used else "released"))
    if changed.rowcount:
        db.execute(update(UserCoupon).where(UserCoupon.id == record.user_coupon_id, UserCoupon.status == "reserved")
            .values(status="used" if used else "available"))


def quote(db, user, code, body):
    from app.services.orders import freight_for
    shop = shop_by_code(db, code)
    quantities = {}
    for item in body.items:
        quantities[item.sku_id] = min(20, quantities.get(item.sku_id, 0) + item.quantity)
    goods = 0
    for sku_id, quantity in quantities.items():
        sku = load_sku_for_shop(db, shop.id, sku_id)
        if not sku or purchase_block(sku, quantity):
            raise HTTPException(400, "商品暂不可购买或库存不足")
        goods += sku.price_cents * quantity
    discount = 0
    if body.user_coupon_id:
        _, _, discount = validate(db, user.id, shop.id, body.user_coupon_id, goods)
    available = []
    for c in list_c(db, code, user):
        c["eligible"] = c["active"] and c["status"] == "available" and goods >= c["threshold_cents"]
        available.append(c)
    freight = freight_for(goods, shop)
    return dict(goods_yuan=yuan(goods), freight_yuan=yuan(freight), discount_yuan=yuan(discount),
                total_yuan=yuan(goods + freight - discount), coupons=available)
