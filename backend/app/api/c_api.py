from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.assistant import assistant
from app.agent.context import Actor, reset_actor, set_actor
from app.core.deps import get_current_user, get_db, get_optional_user, require_customer
from app.models.tables import User
from app.schemas.dto import (
    AddressIn,
    AddressOut,
    CartAdd,
    CartCheckout,
    CartUpdate,
    ChatIn,
    ChatOut,
    HomeOut,
    OrderCreate,
    OrderOut,
    PendingReview,
    ProductOut,
    ReviewIn,
    ReviewOut,
    SavedProductOut,
    SessionOut,
    ShopOut,
)
from app.services.catalog import get_c_product, list_categories, list_c_products, serialize_product, serialize_shop, shop_by_code
from app.services.home import home_content
from app.services.engagement import (
    clear_history,
    favorite_products,
    history_products,
    record_view,
    serialize_saved_list,
    toggle_favorite,
)
from app.services.orders import cancel_order, confirm_order, create_order, list_c_orders, pay_order
from app.services.reviews import create_review, list_reviews, pending_reviews
from app.services.trade import add_cart, cart_view, checkout_cart, create_address, delete_address, list_addresses, remove_cart, update_cart

router = APIRouter(prefix="/c", tags=["c"])


@router.get("/shops/{share_code}", response_model=ShopOut)
def read_shop(share_code: str, db: Session = Depends(get_db)):
    return serialize_shop(shop_by_code(db, share_code))


@router.get("/shops/{share_code}/categories", response_model=list[str])
def read_categories(share_code: str, db: Session = Depends(get_db)):
    return list_categories(db, share_code)


@router.get("/shops/{share_code}/products", response_model=list[ProductOut])
def read_products(
    share_code: str,
    keyword: str = "",
    category: str = "",
    sort: str = "default",
    offset: int = 0,
    limit: int | None = None,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    return list_c_products(
        db, share_code, keyword=keyword, category=category, sort=sort, user=user, offset=offset, limit=limit
    )


@router.get("/shops/{share_code}/home", response_model=HomeOut)
def read_home(
    share_code: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    return home_content(db, share_code, user)


@router.get("/shops/{share_code}/products/{product_id}", response_model=ProductOut)
def read_product(
    share_code: str,
    product_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    product = get_c_product(db, share_code, product_id, user)
    if user is not None and user.role == "customer":
        record_view(user.id, product_id)
    return product


@router.get("/favorites", response_model=list[SavedProductOut])
def read_favorites(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """跨店铺的收藏。下架或禁售的商品也返回，前端按 shelf_label 加标注。"""
    return serialize_saved_list(db, user, favorite_products(db, user))


@router.post("/favorites/{product_id}")
def switch_favorite(
    product_id: int,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return toggle_favorite(db, user, product_id)


@router.get("/history", response_model=list[SavedProductOut])
def read_history(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """浏览记录同样是跨店铺的，只保留最近 7 天。"""
    return serialize_saved_list(db, user, history_products(db, user))


@router.delete("/history")
def wipe_history(user: User = Depends(require_customer)):
    clear_history(user)
    return {"ok": True}


@router.get("/shops/{share_code}/products/{product_id}/reviews", response_model=list[ReviewOut])
def read_reviews(share_code: str, product_id: int, db: Session = Depends(get_db)):
    shop_by_code(db, share_code)
    return list_reviews(db, product_id)


@router.get("/reviews/pending", response_model=list[PendingReview])
def read_pending_reviews(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return pending_reviews(db, user)


@router.post("/reviews", response_model=ReviewOut)
def add_review(body: ReviewIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return create_review(db, user, body)


@router.get("/shops/{share_code}/cart")
def read_cart(share_code: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return cart_view(db, user, share_code)


@router.post("/shops/{share_code}/cart")
def create_cart_item(
    share_code: str,
    body: CartAdd,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return add_cart(db, user, share_code, body)


@router.patch("/cart/{item_id}")
def patch_cart(item_id: int, body: CartUpdate, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return update_cart(db, user, item_id, body)


@router.delete("/cart/{item_id}")
def delete_cart(item_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return remove_cart(db, user, item_id)


@router.post("/shops/{share_code}/cart/checkout", response_model=OrderOut)
def checkout(
    share_code: str,
    body: CartCheckout,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return checkout_cart(db, user, share_code, body)


@router.get("/addresses", response_model=list[AddressOut])
def read_addresses(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return list_addresses(db, user)


@router.post("/addresses", response_model=AddressOut)
def add_address(body: AddressIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return create_address(db, user, body)


@router.delete("/addresses/{address_id}")
def remove_address(address_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    delete_address(db, user, address_id)
    return {"ok": True}


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
    status: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_c_orders(db, user, share_code, status)


@router.post("/orders/{order_no}/pay", response_model=OrderOut)
def pay(order_no: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return pay_order(db, user, order_no)


@router.post("/orders/{order_no}/cancel", response_model=OrderOut)
def cancel(order_no: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return cancel_order(db, user, order_no)


@router.post("/orders/{order_no}/confirm", response_model=OrderOut)
def confirm(order_no: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return confirm_order(db, user, order_no)


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
