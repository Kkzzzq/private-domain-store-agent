from typing import Literal
from datetime import timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.api.op_api import require_operator
from app.api.op_management import audit
from app.core.deps import get_db
from app.core.security import hash_password
from app.models.tables import User, Shop, Review, Product, Address, CartItem, UserCoupon, Coupon, Order, Sku, utcnow
from app.models.governance import AccountRestriction, ShopRestriction, ReviewRestriction, WorkspaceAction
from app.services.catalog import invalidate_catalog_cache

router = APIRouter(prefix='/governance', dependencies=[Depends(require_operator)])


class Control(BaseModel):
    action: str
    reason: str = Field(min_length=2, max_length=200)
    password: str | None = Field(None, min_length=10, max_length=64)


def reason_of(body):
    if len(body.reason.strip()) < 2:
        raise HTTPException(422, '请填写操作原因')
    return body.reason.strip()


@router.post('/accounts/{user_id}')
def control_account(user_id: int, body: Control, actor: User = Depends(require_operator), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, '账号不存在')
    if user_id == actor.id:
        raise HTTPException(409, '请勿在平台管理中禁用或重置当前登录的运营账号')
    if body.action not in ('disable', 'enable', 'reset_password'):
        raise HTTPException(422, '无效账号操作')
    reason = reason_of(body)
    if body.action == 'reset_password' and (not body.password or len(body.password.encode()) > 72):
        raise HTTPException(422, '新密码需10—64字符，且不超过72个UTF-8字节')
    row = db.get(AccountRestriction, user_id)
    if row is None:
        row = AccountRestriction(user_id=user_id)
        db.add(row)
    if body.action == 'reset_password':
        user.password_hash = hash_password(body.password)
    else:
        row.disabled = body.action == 'disable'
    row.revoke_before, row.reason = utcnow(), reason
    row.revoke_before_us = int(row.revoke_before.replace(tzinfo=timezone.utc).timestamp() * 1_000_000)
    audit(db, actor, 'account', user_id, body.action, reason)
    db.commit()
    return {'id': user_id, 'disabled': row.disabled, 'sessions_revoked': True}


@router.post('/shops/{shop_id}')
def control_shop(shop_id: int, body: Control, actor: User = Depends(require_operator), db: Session = Depends(get_db)):
    if not db.get(Shop, shop_id):
        raise HTTPException(404, '店铺不存在')
    if body.action not in ('freeze', 'unfreeze'):
        raise HTTPException(422, '无效店铺操作')
    row = db.get(ShopRestriction, shop_id)
    if row is None:
        row = ShopRestriction(shop_id=shop_id); db.add(row)
    row.blocked, row.reason = body.action == 'freeze', reason_of(body)
    audit(db, actor, 'shop', shop_id, body.action, row.reason)
    db.commit(); invalidate_catalog_cache()
    return {'id': shop_id, 'platform_blocked': row.blocked}


@router.post('/skus/{sku_id}')
def control_sku(sku_id: int, body: Control, actor: User = Depends(require_operator), db: Session = Depends(get_db)):
    row=db.scalar(select(Sku).where(Sku.id==sku_id).with_for_update())
    if row is None: raise HTTPException(404,'规格不存在')
    if body.action not in ('ban','unban'): raise HTTPException(422,'无效规格操作')
    if body.action=='unban' and row.status!='banned': raise HTTPException(409,'该规格未禁售')
    row.status='banned' if body.action=='ban' else 'off'
    audit(db,actor,'sku',sku_id,body.action,reason_of(body));db.commit();invalidate_catalog_cache()
    return {'id':sku_id,'status':row.status}


@router.post('/orders/{order_id}/cancel')
def platform_cancel(order_id: int, body: Control, actor: User = Depends(require_operator), db: Session = Depends(get_db)):
    row=db.get(Order,order_id)
    if row is None: raise HTTPException(404,'订单不存在')
    reason=reason_of(body)
    if body.action!='cancel': raise HTTPException(422,'无效订单操作')
    from app.services.orders import cancel_order
    # Existing atomic pending->cancelled transition restores stock and coupons.
    result=cancel_order(db,db.get(User,row.user_id),row.order_no)
    audit(db,actor,'order',order_id,'cancel_pending',reason);db.commit()
    return result


@router.get('/reviews')
def reviews(shop_id: int | None = None, user_id: int | None = None, page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    if shop_id is None and user_id is None:
        return {'items': [], 'total': 0, 'needs_filter': True}
    query = select(Review).join(Product, Review.product_id == Product.id)
    if shop_id is not None: query = query.where(Product.shop_id == shop_id)
    if user_id is not None: query = query.where(Review.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows=[]
    for r in db.scalars(query.order_by(Review.id.desc()).offset((page-1)*20).limit(20)):
        restriction = db.get(ReviewRestriction, r.id)
        rows.append(dict(id=r.id, product_id=r.product_id, product=db.get(Product,r.product_id).name,
                         user_id=r.user_id, rating=r.rating, content=r.content, hidden=bool(restriction and restriction.hidden), created_at=r.created_at))
    return dict(items=rows, total=total)


@router.post('/reviews/{review_id}')
def control_review(review_id: int, body: Control, actor: User = Depends(require_operator), db: Session = Depends(get_db)):
    if not db.get(Review, review_id): raise HTTPException(404, '评价不存在')
    if body.action not in ('hide','show'): raise HTTPException(422, '无效评价操作')
    row=db.get(ReviewRestriction,review_id)
    if row is None: row=ReviewRestriction(review_id=review_id);db.add(row)
    row.hidden, row.reason=body.action=='hide',reason_of(body)
    audit(db,actor,'review',review_id,body.action,row.reason)
    db.commit();invalidate_catalog_cache()
    return {'id':review_id,'hidden':row.hidden}


@router.get('/customers/{user_id}/{kind}')
def customer_records(user_id: int, kind: Literal['addresses','cart','coupons','history'], page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    user=db.get(User,user_id)
    if not user: raise HTTPException(404,'账号不存在')
    if kind=='history':
        from app.services.engagement import history_products
        products=history_products(db,user)
        return dict(total=len(products),items=[dict(id=p.id,name=p.name,shop_id=p.shop_id,status=p.status) for p in products[(page-1)*20:page*20]])
    model={'addresses':Address,'cart':CartItem,'coupons':UserCoupon}[kind]
    query=select(model).where(model.user_id==user_id)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    items=[]
    for row in db.scalars(query.order_by(model.id.desc()).offset((page-1)*20).limit(20)):
        if kind=='addresses':
            items.append(dict(id=row.id,receiver=row.receiver,phone=row.phone,region=row.region,detail=row.detail,is_default=row.is_default))
        elif kind=='cart':
            items.append(dict(id=row.id,shop_id=row.shop_id,product=row.sku.product.name,spec=row.sku.spec,quantity=row.quantity,price_cents=row.sku.price_cents,stock=row.sku.stock))
        else:
            coupon=db.get(Coupon,row.coupon_id)
            items.append(dict(id=row.id,shop_id=coupon.shop_id,name=coupon.name,status=row.status,amount_cents=coupon.amount_cents,threshold_cents=coupon.threshold_cents,ends_at=coupon.ends_at))
    return dict(items=items,total=total)


@router.get('/workspace-actions')
def workspace_actions(shop_id: int | None = None, page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    query=select(WorkspaceAction)
    if shop_id is not None: query=query.where(WorkspaceAction.shop_id==shop_id)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return dict(total=total,items=[dict(id=r.id,operator_id=r.operator_id,shop_id=r.shop_id,method=r.method,
                resource=r.resource,reason=r.reason,status=r.status,created_at=r.created_at)
                for r in db.scalars(query.order_by(WorkspaceAction.id.desc()).offset((page-1)*20).limit(20))])
