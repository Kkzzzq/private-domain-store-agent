from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.assistant import assistant
from app.agent.context import Actor, reset_actor, set_actor
from app.core.deps import get_current_user, get_db, require_customer
from app.models.tables import User
from app.schemas.dto import ChatIn, ChatOut, OrderCreate, OrderOut, ProductOut, SessionOut, ShopOut
from app.services.catalog import list_c_products, serialize_shop, shop_by_code
from app.services.orders import create_order, list_c_orders, pay_order

router = APIRouter(prefix="/c", tags=["c"])


@router.get("/shops/{share_code}", response_model=ShopOut)
def read_shop(share_code: str, db: Session = Depends(get_db)):
    return serialize_shop(shop_by_code(db, share_code))


@router.get("/shops/{share_code}/products", response_model=list[ProductOut])
def read_products(share_code: str, db: Session = Depends(get_db)):
    return list_c_products(db, share_code)


@router.post("/shops/{share_code}/orders", response_model=OrderOut)
def add_order(
    share_code: str,
    body: OrderCreate,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return create_order(db, user, share_code, body)


@router.get("/orders", response_model=list[OrderOut])
def read_orders(
    share_code: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_c_orders(db, user, share_code)


@router.post("/orders/{order_no}/pay", response_model=OrderOut)
def pay(order_no: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return pay_order(db, user, order_no)


@router.post("/shops/{share_code}/chat", response_model=ChatOut)
def chat(
    share_code: str,
    body: ChatIn,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    shop = shop_by_code(db, share_code)
    token = set_actor(db, Actor(user.id, user.role, user.username, shop.id))
    try:
        return assistant.chat(user_id=user.id, shop_id=shop.id, session_id=body.session_id, message=body.message.strip())
    finally:
        reset_actor(token)


@router.get("/shops/{share_code}/sessions/{session_id}", response_model=SessionOut)
def read_session(
    share_code: str,
    session_id: str,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    shop = shop_by_code(db, share_code)
    return assistant.read_session(user.id, shop.id, session_id)
