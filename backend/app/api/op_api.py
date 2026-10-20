from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.tables import User, Shop, Product, Sku, Order, Coupon, AgentToolLog, utcnow
from app.models.support import AfterSale
from app.models.operations import Operator, OperationLog
from app.services.catalog import invalidate_catalog_cache

router = APIRouter(prefix='/op', tags=['operations'])


def require_operator(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Operator, user.id):
        raise HTTPException(403, '此账号没有平台运营权限')
    return user


@router.get('/me')
def me(user: User = Depends(require_operator)):
    return {'id': user.id, 'nickname': user.nickname, 'username': user.username}


@router.get('/overview')
def overview(user: User = Depends(require_operator), db: Session = Depends(get_db)):
    count = lambda model, *where: db.scalar(select(func.count()).select_from(model).where(*where)) or 0
    paid = Order.status.in_(['paid', 'shipped', 'completed'])
    # Shanghai calendar day, stored database timestamps are UTC.
    today = (utcnow() + timedelta(hours=8)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=8)
    trend = []
    for offset in range(6, -1, -1):
        start = today - timedelta(days=offset)
        trend.append({'day': (start + timedelta(hours=8)).strftime('%m-%d'), 'orders': count(Order, Order.created_at >= start, Order.created_at < start + timedelta(days=1)),
                      'paid_cents': db.scalar(select(func.coalesce(func.sum(Order.total_cents), 0)).where(paid, Order.created_at >= start, Order.created_at < start + timedelta(days=1)))})
    return {'shops': count(Shop), 'products': count(Product), 'orders': count(Order),
            'paid_cents': db.scalar(select(func.coalesce(func.sum(Order.total_cents), 0)).where(paid)),
            'pending_ship': count(Order, Order.status == 'paid'), 'low_stock': count(Sku, Sku.status == 'on', Sku.stock <= 5),
            'banned': count(Product, Product.status == 'banned'), 'after_sales': count(AfterSale, AfterSale.status == 'requested'), 'trend': trend}


RESOURCES = {'shops': Shop, 'products': Product, 'orders': Order, 'coupons': Coupon, 'after-sales': AfterSale, 'agent-logs': AgentToolLog, 'operation-logs': OperationLog}


@router.get('/records/{resource}')
def records(resource: str, q: str = '', status: str = '', shop_id: int | None = None,
            page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
            user: User = Depends(require_operator), db: Session = Depends(get_db)):
    model = RESOURCES.get(resource)
    if model is None:
        raise HTTPException(404, '没有此列表')
    query = select(model)
    if shop_id is not None and hasattr(model, 'shop_id'):
        query = query.where(model.shop_id == shop_id)
    if status and hasattr(model, 'status'):
        query = query.where(model.status == status)
    if q.strip():
        field = getattr(model, 'name', None)
        if field is None:
            field = getattr(model, 'order_no', None)
        if field is None:
            field = getattr(model, 'tool', None)
        if field is None:
            field = getattr(model, 'reason', None)
        if field is not None:
            query = query.where(field.contains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = []
    for row in db.scalars(query.order_by(model.id.desc()).offset((page-1)*size).limit(size)):
        fields = {
            'shops': ['id', 'name', 'share_code', 'status', 'created_at'],
            'products': ['id', 'shop_id', 'name', 'category', 'status', 'sales_count'],
            'orders': ['id', 'shop_id', 'order_no', 'status', 'total_cents', 'freight_cents', 'created_at'],
            'coupons': ['id', 'shop_id', 'name', 'threshold_cents', 'amount_cents', 'claimed_count', 'total_count', 'enabled', 'ends_at'],
            'after-sales': ['id', 'order_id', 'kind', 'reason', 'status', 'created_at'],
            'agent-logs': ['id', 'shop_id', 'tool', 'ok', 'latency_ms', 'flag', 'created_at'],
            'operation-logs': ['id', 'user_id', 'product_id', 'action', 'reason', 'created_at'],
        }[resource]
        item = {key: getattr(row, key) for key in fields}
        if 'shop_id' in item:
            shop = db.get(Shop, item['shop_id'])
            item['shop_name'] = shop.name if shop else '—'
        if resource == 'products':
            item['stock'] = sum(s.stock for s in row.skus)
        items.append(item)
    return {'items': items, 'total': total, 'page': page, 'size': size}


class ModerateIn(BaseModel):
    action: Literal['ban', 'release']
    reason: str = Field(min_length=2, max_length=200)


@router.post('/products/{product_id}/moderate')
def moderate(product_id: int, body: ModerateIn, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    if len(body.reason.strip()) < 2:
        raise HTTPException(422, '请填写至少两个字的操作原因')
    product = db.scalar(select(Product).where(Product.id == product_id).with_for_update())
    if product is None:
        raise HTTPException(404, '商品不存在')
    if body.action == 'release' and product.status != 'banned':
        raise HTTPException(409, '商品当前未禁售')
    product.status = 'banned' if body.action == 'ban' else 'off'
    db.add(OperationLog(user_id=user.id, product_id=product.id, action=body.action, reason=body.reason.strip()))
    db.commit()
    invalidate_catalog_cache()
    return {'id': product.id, 'status': product.status}
