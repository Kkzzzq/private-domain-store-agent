from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_merchant
from app.models.tables import User
from app.rag.knowledge import reindex_knowledge
from app.schemas.dto import (
    OrderOut,
    ProductIn,
    ProductOut,
    ProductUpdate,
    ReindexOut,
    ShopOut,
    ShopUpdate,
    SkuUpdate,
    StatusAction,
)
from app.services.catalog import (
    change_product_status,
    change_sku_status,
    create_product,
    list_b_products,
    merchant_shop,
    serialize_shop,
    update_product,
    update_shop,
    update_sku,
)
from app.services.orders import list_b_orders, ship_order

router = APIRouter(prefix="/b", tags=["b"])


@router.get("/shop", response_model=ShopOut)
def read_shop(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return serialize_shop(merchant_shop(db, user))


@router.patch("/shop", response_model=ShopOut)
def patch_shop(body: ShopUpdate, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return update_shop(db, user, body)


@router.get("/products", response_model=list[ProductOut])
def read_products(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return list_b_products(db, user)


@router.post("/products", response_model=ProductOut)
def add_product(body: ProductIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return create_product(db, user, body)


@router.patch("/products/{product_id}", response_model=ProductOut)
def patch_product(
    product_id: int,
    body: ProductUpdate,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return update_product(db, user, product_id, body)


@router.post("/products/{product_id}/status", response_model=ProductOut)
def product_status(
    product_id: int,
    body: StatusAction,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return change_product_status(db, user, product_id, body.action)


@router.patch("/skus/{sku_id}", response_model=ProductOut)
def patch_sku(
    sku_id: int,
    body: SkuUpdate,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return update_sku(db, user, sku_id, body)


@router.post("/skus/{sku_id}/status", response_model=ProductOut)
def sku_status(
    sku_id: int,
    body: StatusAction,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return change_sku_status(db, user, sku_id, body.action)


@router.get("/orders", response_model=list[OrderOut])
def read_orders(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return list_b_orders(db, user)


@router.post("/orders/{order_no}/ship", response_model=OrderOut)
def ship(order_no: str, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return ship_order(db, user, order_no)


@router.post("/knowledge/reindex", response_model=ReindexOut)
def reindex(user: User = Depends(require_merchant)):
    del user
    return reindex_knowledge()
