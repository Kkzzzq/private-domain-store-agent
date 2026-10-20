from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from app.api.op_api import require_operator
from app.core.deps import get_db
from app.models.tables import User, Shop, Product, Order, AccountClosure, CouponOrder, utcnow
from app.models.account import MerchantAccess, can_manage_store
from app.models.operations import Operator
from app.models.platform_audit import PlatformAudit
from app.models.support import Shipment, AfterSale
from app.services.catalog import invalidate_catalog_cache

router = APIRouter(prefix='/platform', dependencies=[Depends(require_operator)])


def audit(db, actor, kind, target_id, action, reason):
    db.add(PlatformAudit(operator_id=actor.id, target_type=kind, target_id=target_id, action=action, reason=reason))


def account_out(db, row):
    shop = db.scalar(select(Shop).where(Shop.merchant_id == row.id))
    return dict(id=row.id, username=row.username, nickname=row.nickname,
                merchant_enabled=can_manage_store(db, row), operator=bool(db.get(Operator, row.id)),
                closed=bool(db.get(AccountClosure, row.id)), shop_id=shop.id if shop else None,
                shop_name=shop.name if shop else '未开店', created_at=row.created_at)


@router.get('/accounts')
def accounts(q: str = '', page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = select(User)
    if q.strip():
        query = query.where(or_(User.username.contains(q.strip(), autoescape=True), User.nickname.contains(q.strip(), autoescape=True)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return dict(items=[account_out(db, r) for r in db.scalars(query.order_by(User.id.desc()).offset((page-1)*size).limit(size))], total=total)


class AccountUpdate(BaseModel):
    nickname: str | None = Field(None, min_length=1, max_length=32)
    merchant_enabled: bool | None = None
    reason: str = Field(min_length=2, max_length=200)

    @field_validator('nickname', 'reason')
    @classmethod
    def strip_value(cls, value):
        if value is not None and not value.strip():
            raise ValueError('内容不能为空')
        return value.strip() if value is not None else None


@router.patch('/accounts/{account_id}')
def update_account(account_id: int, body: AccountUpdate, actor: User = Depends(require_operator), db: Session = Depends(get_db)):
    row = db.get(User, account_id)
    if row is None:
        raise HTTPException(404, '账号不存在')
    if db.get(AccountClosure, row.id):
        raise HTTPException(409, '账号已注销')
    if len(body.reason.strip()) < 2:
        raise HTTPException(422, '请填写至少两个字的操作原因')
    if body.nickname is not None:
        row.nickname = body.nickname
    if body.merchant_enabled is not None:
        access = db.get(MerchantAccess, row.id)
        if access is None:
            db.add(MerchantAccess(user_id=row.id, enabled=body.merchant_enabled))
        else:
            access.enabled = body.merchant_enabled
    audit(db, actor, 'account', row.id, 'update_account', body.reason)
    db.commit()
    return account_out(db, row)


@router.get('/shops')
def shops(q: str = '', page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = select(Shop)
    if q.strip():
        query = query.where(or_(Shop.name.contains(q.strip(), autoescape=True), Shop.share_code.contains(q.strip(), autoescape=True)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = []
    for shop in db.scalars(query.order_by(Shop.id.desc()).offset((page-1)*size).limit(size)):
        owner = db.get(User, shop.merchant_id)
        rows.append(dict(id=shop.id, name=shop.name, status=shop.status, share_code=shop.share_code,
                         owner=owner.username if owner else '—', owner_id=shop.merchant_id,
                         products=db.scalar(select(func.count()).select_from(Product).where(Product.shop_id == shop.id)),
                         orders=db.scalar(select(func.count()).select_from(Order).where(Order.shop_id == shop.id))))
    return dict(items=rows, total=total)


@router.get('/shops/{shop_id}')
def shop_detail(shop_id: int, db: Session = Depends(get_db)):
    row = db.get(Shop, shop_id)
    if row is None:
        raise HTTPException(404, '店铺不存在')
    owner = db.get(User, row.merchant_id)
    return dict(id=row.id, name=row.name, notice=row.notice, status=row.status, share_code=row.share_code,
                owner=account_out(db, owner), created_at=row.created_at)


class ShopUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    notice: str = Field(default='', max_length=2000)
    status: str = Field(pattern='^(open|closed)$')
    reason: str = Field(min_length=2, max_length=200)


@router.patch('/shops/{shop_id}')
def update_shop(shop_id: int, body: ShopUpdate, actor: User = Depends(require_operator), db: Session = Depends(get_db)):
    row = db.get(Shop, shop_id)
    if row is None:
        raise HTTPException(404, '店铺不存在')
    if not body.name.strip() or len(body.reason.strip()) < 2:
        raise HTTPException(422, '店铺名称和操作原因不能为空')
    row.name, row.notice, row.status = body.name.strip(), body.notice.strip(), body.status
    audit(db, actor, 'shop', row.id, 'update_shop', body.reason.strip())
    db.commit()
    invalidate_catalog_cache()
    return {'id': row.id, 'name': row.name, 'status': row.status}


@router.get('/orders')
def orders(q: str = '', shop_id: int | None = None, status: str = '', days: int = Query(7, ge=1, le=365),
           shipped_only: bool = False, after_sales_only: bool = False,
           page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    if shop_id is None and not q.strip():
        return {'items': [], 'total': 0, 'needs_filter': True}
    query = select(Order)
    if shop_id is not None:
        query = query.where(Order.shop_id == shop_id)
    if q.strip():
        term = q.strip()
        buyer_ids = select(User.id).where(User.username == term)
        shipment_ids = select(Shipment.order_id).where(Shipment.tracking_number.contains(term, autoescape=True))
        query = query.where(or_(Order.order_no.contains(term, autoescape=True), Order.user_id.in_(buyer_ids), Order.id.in_(shipment_ids)))
    else:
        query = query.where(Order.created_at >= utcnow() - timedelta(days=days))
    if status:
        query = query.where(Order.status == status)
    if shipped_only:
        query = query.where(Order.id.in_(select(Shipment.order_id)))
    if after_sales_only:
        query = query.where(Order.id.in_(select(AfterSale.order_id)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    result = []
    for row in db.scalars(query.order_by(Order.created_at.desc(), Order.id.desc()).offset((page-1)*size).limit(size)):
        shipment = db.scalar(select(Shipment).where(Shipment.order_id == row.id))
        result.append(dict(id=row.id, order_no=row.order_no, shop_id=row.shop_id, shop_name=row.shop.name,
                           buyer=row.buyer.username, status=row.status, total_cents=row.total_cents,
                           created_at=row.created_at, carrier=shipment.carrier if shipment else '',
                           tracking_number=shipment.tracking_number if shipment else '', shipment_status=shipment.status if shipment else 'unshipped'))
    return {'items': result, 'total': total, 'needs_filter': False}


@router.get('/products/{product_id}')
def product_detail(product_id: int, db: Session = Depends(get_db)):
    row = db.get(Product, product_id)
    if row is None:
        raise HTTPException(404, '商品不存在')
    return dict(id=row.id, name=row.name, category=row.category, description=row.description, status=row.status,
                shop_id=row.shop_id, shop_name=row.shop.name,
                skus=[dict(id=s.id, spec=s.spec, price_cents=s.price_cents, stock=s.stock, status=s.status) for s in row.skus])


@router.get('/orders/{order_id}')
def order_detail(order_id: int, db: Session = Depends(get_db)):
    row = db.get(Order, order_id)
    if row is None:
        raise HTTPException(404, '订单不存在')
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == row.id))
    sale = db.scalar(select(AfterSale).where(AfterSale.order_id == row.id))
    coupon = db.scalar(select(CouponOrder).where(CouponOrder.order_id == row.id))
    return dict(id=row.id, order_no=row.order_no, shop_id=row.shop_id, shop_name=row.shop.name,
                buyer={'id': row.buyer.id, 'username': row.buyer.username, 'nickname': row.buyer.nickname},
                status=row.status, total_cents=row.total_cents, freight_cents=row.freight_cents,
                discount_cents=coupon.discount_cents if coupon else 0, receiver=row.receiver, phone=row.phone,
                address=row.address, created_at=row.created_at,
                items=[dict(name=i.product_name, spec=i.sku_spec, price_cents=i.price_cents, quantity=i.quantity,
                            subtotal_cents=i.price_cents*i.quantity) for i in row.items],
                shipment=dict(carrier=shipment.carrier, tracking_number=shipment.tracking_number, status=shipment.status,
                              events=shipment.events, created_at=shipment.created_at) if shipment else None,
                after_sale=dict(kind=sale.kind, reason=sale.reason, status=sale.status,
                                return_carrier=sale.return_carrier, return_tracking=sale.return_tracking, events=sale.events) if sale else None)


@router.get('/audits')
def audits(page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(PlatformAudit))
    return dict(total=total, items=[dict(id=r.id, operator_id=r.operator_id, target_type=r.target_type,
                target_id=r.target_id, action=r.action, reason=r.reason, created_at=r.created_at)
                for r in db.scalars(select(PlatformAudit).order_by(PlatformAudit.id.desc()).offset((page-1)*20).limit(20))])
