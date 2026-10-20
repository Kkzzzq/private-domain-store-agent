from datetime import timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db, require_customer, require_merchant
from app.models.tables import Order, Shop, User, utcnow
from app.models.support import Conversation, Message, Shipment, AfterSale
from app.services.catalog import merchant_shop, shop_by_code

router = APIRouter(prefix='/support', tags=['human support'])


def stamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat()


def event(user, text):
    return dict(at=stamp(utcnow()), role=user.actor_role, text=text)


def owned_order(db, user, number, lock=False):
    query = select(Order).where(Order.order_no == number)
    if user.actor_role == 'customer':
        query = query.where(Order.user_id == user.id)
    else:
        query = query.where(Order.shop_id == merchant_shop(db, user).id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if not row:
        raise HTTPException(404, '没有找到这个订单')
    return row


def owned_conversation(db, user, conversation_id):
    row = db.get(Conversation, conversation_id)
    if not row or (user.actor_role == 'customer' and row.customer_id != user.id) or (
        user.actor_role == 'merchant' and row.shop_id != merchant_shop(db, user).id):
        raise HTTPException(404, '没有找到这个会话')
    return row


def conversation_payload(db, user, row):
    last = db.scalar(select(Message).where(Message.conversation_id == row.id).order_by(Message.id.desc()).limit(1))
    read = row.buyer_read if user.actor_role == 'customer' else row.merchant_read
    unread = db.scalar(select(func.count(Message.id)).where(Message.conversation_id == row.id,
        Message.sender_role != user.actor_role, Message.id > read))
    name = db.get(Shop, row.shop_id).name if user.actor_role == 'customer' else db.get(User, row.customer_id).nickname
    return dict(id=row.id, name=name, customer_username=db.get(User, row.customer_id).username,
        unread=unread, last_message=last.content[:100] if last else '', updated_at=stamp(row.updated_at))


@router.post('/shops/{code}/conversation')
def start(code: str, user=Depends(require_customer), db: Session=Depends(get_db)):
    shop = shop_by_code(db, code)
    return ensure_conversation(db, user, shop.id, user.id)


def ensure_conversation(db, user, shop_id, customer_id):
    row = db.scalar(select(Conversation).where(Conversation.shop_id == shop_id, Conversation.customer_id == customer_id))
    if not row:
        row = Conversation(shop_id=shop_id, customer_id=customer_id)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.scalar(select(Conversation).where(Conversation.shop_id == shop_id, Conversation.customer_id == customer_id))
    return conversation_payload(db, user, row)


@router.post('/orders/{number}/conversation')
def order_conversation(number: str, user=Depends(get_current_user), db: Session=Depends(get_db)):
    order = owned_order(db, user, number)
    return ensure_conversation(db, user, order.shop_id, order.user_id)


@router.get('/conversations')
def conversations(user=Depends(get_current_user), db: Session=Depends(get_db)):
    query = select(Conversation)
    query = query.where(Conversation.customer_id == user.id) if user.actor_role == 'customer' else query.where(Conversation.shop_id == merchant_shop(db, user).id)
    return [conversation_payload(db, user, row) for row in db.scalars(query.order_by(Conversation.updated_at.desc(), Conversation.id.desc())).all()]


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    client_id: str = Field(min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')
    order_no: str = Field(default='', max_length=32)

    @field_validator('content')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('消息不能为空')
        return value.strip()


def message_payload(row):
    return dict(id=row.id, sender_role=row.sender_role, content=row.content, order_no=row.order_no, created_at=stamp(row.created_at))


@router.get('/conversations/{conversation_id}/messages')
def messages(conversation_id: int, after: int=Query(0, ge=0), before: int | None=Query(None, ge=1), user=Depends(get_current_user), db: Session=Depends(get_db)):
    owned_conversation(db, user, conversation_id)
    query = select(Message).where(Message.conversation_id == conversation_id, Message.id > after)
    if before:
        query = query.where(Message.id < before)
    # Initial history loads the most recent page; subsequent polling never skips messages.
    query = query.order_by(Message.id.asc() if after else Message.id.desc()).limit(100)
    rows = list(db.scalars(query).all())
    return [message_payload(row) for row in (rows if after else reversed(rows))]


@router.post('/conversations/{conversation_id}/messages')
def send(conversation_id: int, body: MessageIn, user=Depends(get_current_user), db: Session=Depends(get_db)):
    conv = owned_conversation(db, user, conversation_id)
    if body.order_no:
        order = owned_order(db, user, body.order_no)
        if order.shop_id != conv.shop_id or order.user_id != conv.customer_id:
            raise HTTPException(400, '订单与当前会话不匹配')
    existing = db.scalar(select(Message).where(Message.conversation_id == conv.id, Message.client_id == body.client_id))
    if existing:
        if existing.sender_id != user.id or existing.sender_role != user.actor_role:
            raise HTTPException(409, '消息标识冲突')
        return message_payload(existing)
    row = Message(conversation_id=conv.id, sender_id=user.id, sender_role=user.actor_role,
        content=body.content, order_no=body.order_no, client_id=body.client_id)
    db.add(row)
    conv.updated_at = utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Message).where(Message.conversation_id == conv.id, Message.client_id == body.client_id))
        if not existing or existing.sender_id != user.id or existing.sender_role != user.actor_role:
            raise HTTPException(409, '消息标识冲突')
        return message_payload(existing)
    return message_payload(row)


class ReadIn(BaseModel):
    message_id: int = Field(ge=0)


@router.post('/conversations/{conversation_id}/read')
def mark_read(conversation_id: int, body: ReadIn, user=Depends(get_current_user), db: Session=Depends(get_db)):
    row = owned_conversation(db, user, conversation_id)
    if body.message_id and not db.scalar(select(Message.id).where(Message.id == body.message_id, Message.conversation_id == row.id)):
        raise HTTPException(400, '消息不属于该会话')
    column = Conversation.buyer_read if user.actor_role == 'customer' else Conversation.merchant_read
    db.execute(update(Conversation).where(Conversation.id == row.id, column < body.message_id).values({column.key:body.message_id}))
    db.commit()
    return {'ok':True}


class ShippingIn(BaseModel):
    carrier: str = Field(min_length=1, max_length=40)
    tracking_number: str = Field(min_length=6, max_length=64, pattern=r'^[A-Za-z0-9-]+$')
    @field_validator('carrier')
    @classmethod
    def valid_carrier(cls, value):
        if not value.strip():
            raise ValueError('请填写快递公司')
        return value.strip()


class TrackingIn(BaseModel):
    status: Literal['transit','delivered','exception']
    description: str = Field(min_length=1, max_length=300)


def shipment_payload(row):
    return None if not row else dict(carrier=row.carrier, tracking_number=row.tracking_number, status=row.status,
        events=row.events, source='merchant', created_at=stamp(row.created_at))


@router.get('/orders/{number}/shipment')
def shipment(number: str, user=Depends(get_current_user), db: Session=Depends(get_db)):
    order = owned_order(db, user, number)
    return shipment_payload(db.scalar(select(Shipment).where(Shipment.order_id == order.id)))


@router.put('/orders/{number}/shipment')
def ship(number: str, body: ShippingIn, user=Depends(require_merchant), db: Session=Depends(get_db)):
    order = owned_order(db, user, number, True)
    if order.status not in ('paid', 'shipped'):
        raise HTTPException(409, '只有已付款或已发货订单可以填写物流')
    row = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
    if row and row.status == 'delivered':
        raise HTTPException(409, '已签收的运单不能修改')
    if not row:
        row = Shipment(order_id=order.id, **body.model_dump(), events=[])
        db.add(row)
    else:
        row.carrier, row.tracking_number = body.carrier, body.tracking_number
    row.events = [*row.events, event(user, f'填写运单：{body.carrier} {body.tracking_number}')]
    order.status = 'shipped'
    db.commit()
    return shipment_payload(row)


@router.post('/orders/{number}/shipment/events')
def tracking(number: str, body: TrackingIn, user=Depends(require_merchant), db: Session=Depends(get_db)):
    order = owned_order(db, user, number, True)
    row = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
    if not row or row.status == 'delivered':
        raise HTTPException(409, '请先填写运单，已签收运单不能再追加状态')
    row.status = body.status
    row.events = [*row.events, event(user, body.description.strip())]
    db.commit()
    return shipment_payload(row)


class AfterSaleIn(BaseModel):
    kind: Literal['return','exchange','repair','other']
    reason: str = Field(min_length=3, max_length=500)


class ProcessIn(BaseModel):
    action: Literal['accept','reject','resolve','withdraw','return_ship']
    note: str = Field(min_length=2, max_length=500)
    carrier: str = Field(default='', max_length=40)
    tracking_number: str = Field(default='', max_length=64, pattern=r'^[A-Za-z0-9-]*$')


def ticket_payload(db, row):
    order = db.get(Order, row.order_id)
    return dict(id=row.id, order_no=order.order_no, kind=row.kind, reason=row.reason, status=row.status,
        return_carrier=row.return_carrier, return_tracking=row.return_tracking, events=row.events, created_at=stamp(row.created_at))


@router.get('/after-sales')
def tickets(user=Depends(get_current_user), db: Session=Depends(get_db)):
    query = select(AfterSale).join(Order, Order.id == AfterSale.order_id)
    query = query.where(Order.user_id == user.id) if user.actor_role == 'customer' else query.where(Order.shop_id == merchant_shop(db, user).id)
    return [ticket_payload(db, row) for row in db.scalars(query.order_by(AfterSale.id.desc())).all()]


@router.post('/orders/{number}/after-sale')
def request_after_sale(number: str, body: AfterSaleIn, user=Depends(require_customer), db: Session=Depends(get_db)):
    order = owned_order(db, user, number, True)
    if order.status not in ('paid','shipped','completed'):
        raise HTTPException(409, '只有已付款订单可以申请售后')
    if db.scalar(select(AfterSale.id).where(AfterSale.order_id == order.id)):
        raise HTTPException(409, '该订单已有售后记录，请联系商家继续处理')
    if not body.reason.strip():
        raise HTTPException(422, '请填写原因')
    row = AfterSale(order_id=order.id, kind=body.kind, reason=body.reason.strip(), events=[event(user, body.reason.strip())])
    db.add(row)
    db.commit()
    return ticket_payload(db, row)


@router.post('/after-sales/{ticket_id}/process')
def process(ticket_id: int, body: ProcessIn, user=Depends(get_current_user), db: Session=Depends(get_db)):
    row = db.scalar(select(AfterSale).where(AfterSale.id == ticket_id).with_for_update())
    if not row:
        raise HTTPException(404, '没有找到售后单')
    owned_order(db, user, db.get(Order, row.order_id).order_no)
    transitions = {'accept':('requested','accepted'), 'reject':('requested','rejected'),
        'resolve':(('accepted','return_shipped'),'resolved'), 'withdraw':('requested','withdrawn'),
        'return_ship':('accepted','return_shipped')}
    required, target = transitions[body.action]
    allowed_role = 'customer' if body.action in ('withdraw','return_ship') else 'merchant'
    if user.actor_role != allowed_role:
        raise HTTPException(403, '当前账号不能执行此操作')
    if row.status not in (required if isinstance(required, tuple) else (required,)):
        raise HTTPException(409, '售后状态已变更，请刷新后重试')
    if not body.note.strip():
        raise HTTPException(422, '请填写处理说明')
    if body.action == 'return_ship':
        if row.kind not in ('return','exchange') or not body.carrier.strip() or len(body.tracking_number) < 6:
            raise HTTPException(422, '请填写退回快递公司与运单号')
        row.return_carrier, row.return_tracking = body.carrier.strip(), body.tracking_number
    row.status = target
    row.events = [*row.events, event(user, body.note.strip())]
    db.commit()
    return ticket_payload(db, row)
