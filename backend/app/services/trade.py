from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.tables import Address, CartItem, Product, Sku, User
from app.schemas.dto import AddressIn, CartAdd, CartCheckout, CartUpdate, OrderCreate, OrderLine
from app.services.catalog import load_sku_for_shop, shop_by_code, yuan
from app.services.orders import create_order, freight_for
from app.services.shelf import purchase_block


def _cart_rows(db: Session, user: User, shop_id: int) -> list[CartItem]:
    return list(
        db.scalars(
            select(CartItem)
            .options(joinedload(CartItem.sku).joinedload(Sku.product).joinedload(Product.shop))
            .where(CartItem.user_id == user.id, CartItem.shop_id == shop_id)
            .order_by(CartItem.id.asc())
        ).unique().all()
    )


def _serialize_row(row: CartItem) -> dict:
    sku = row.sku
    product = sku.product
    reason = purchase_block(sku, row.quantity)
    return {
        "id": row.id,
        "sku_id": sku.id,
        "product_id": product.id,
        "product_name": product.name,
        "spec": sku.spec,
        "image_url": product.image_url,
        "price_yuan": yuan(sku.price_cents),
        "quantity": row.quantity,
        "stock": sku.stock,
        "available": reason is None,
        "reason": reason or "",
    }


def cart_view(db: Session, user: User, share_code: str) -> dict:
    shop = shop_by_code(db, share_code)
    items = [_serialize_row(row) for row in _cart_rows(db, user, shop.id)]
    goods = sum(int(round(item["price_yuan"] * 100)) * item["quantity"] for item in items if item["available"])
    freight = freight_for(goods) if any(item["available"] for item in items) else 0
    return {
        "items": items,
        "goods_yuan": yuan(goods),
        "freight_yuan": yuan(freight),
        "total_yuan": yuan(goods + freight),
    }


def add_cart(db: Session, user: User, share_code: str, body: CartAdd) -> dict:
    shop = shop_by_code(db, share_code)
    sku = load_sku_for_shop(db, shop.id, body.sku_id)
    if sku is None:
        raise HTTPException(status_code=400, detail="没有找到这个商品")
    existing = db.scalar(select(CartItem).where(CartItem.user_id == user.id, CartItem.sku_id == sku.id))
    quantity = body.quantity if existing is None else min(20, existing.quantity + body.quantity)
    reason = purchase_block(sku, quantity)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    if existing is None:
        db.add(CartItem(user_id=user.id, shop_id=shop.id, sku_id=sku.id, quantity=quantity))
    else:
        existing.quantity = quantity
    db.commit()
    return cart_view(db, user, share_code)


def update_cart(db: Session, user: User, item_id: int, body: CartUpdate) -> dict:
    row = db.get(CartItem, item_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="购物车里没有这件商品")
    sku = load_sku_for_shop(db, row.shop_id, row.sku_id)
    if sku is None:
        raise HTTPException(status_code=400, detail="没有找到这个商品")
    reason = purchase_block(sku, body.quantity)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    row.quantity = body.quantity
    db.commit()
    return cart_view(db, user, sku.product.shop.share_code)


def remove_cart(db: Session, user: User, item_id: int) -> dict:
    row = db.scalar(
        select(CartItem).options(joinedload(CartItem.shop)).where(CartItem.id == item_id, CartItem.user_id == user.id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="购物车里没有这件商品")
    share_code = row.shop.share_code
    db.delete(row)
    db.commit()
    return cart_view(db, user, share_code)


def checkout_cart(db: Session, user: User, share_code: str, body: CartCheckout) -> dict:
    shop = shop_by_code(db, share_code)
    rows = _cart_rows(db, user, shop.id)
    if body.cart_item_ids:
        chosen = {item_id for item_id in body.cart_item_ids}
        rows = [row for row in rows if row.id in chosen]
    rows = [row for row in rows if purchase_block(row.sku, row.quantity) is None]
    if not rows:
        raise HTTPException(status_code=400, detail="没有可结算的商品")
    order = create_order(
        db,
        user,
        share_code,
        OrderCreate(
            items=[OrderLine(sku_id=row.sku_id, quantity=row.quantity) for row in rows],
            address=body.address,
            receiver=body.receiver,
            phone=body.phone,
        ),
    )
    for row in rows:
        current = db.get(CartItem, row.id)
        if current is not None:
            db.delete(current)
    db.commit()
    return order


def list_addresses(db: Session, user: User) -> list[dict]:
    rows = db.scalars(select(Address).where(Address.user_id == user.id).order_by(Address.is_default.desc(), Address.id.desc())).all()
    return [_address(row) for row in rows]


def _address(row: Address) -> dict:
    return {
        "id": row.id,
        "receiver": row.receiver,
        "phone": row.phone,
        "region": row.region,
        "detail": row.detail,
        "is_default": row.is_default,
    }


def create_address(db: Session, user: User, body: AddressIn) -> dict:
    if body.is_default:
        for row in db.scalars(select(Address).where(Address.user_id == user.id)).all():
            row.is_default = False
    row = Address(
        user_id=user.id,
        receiver=body.receiver.strip(),
        phone=body.phone.strip(),
        region=body.region.strip(),
        detail=body.detail.strip(),
        is_default=body.is_default or db.scalar(select(Address).where(Address.user_id == user.id)) is None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _address(row)


def delete_address(db: Session, user: User, address_id: int) -> None:
    row = db.get(Address, address_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="没有找到这个地址")
    db.delete(row)
    db.commit()
