"""买家侧的收藏和浏览历史。历史放 Redis，收藏落库。"""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.redis_client import get_redis
from app.models.tables import Favorite, Product, Shop, User

HISTORY_LIMIT = 20


def favorite_ids(db: Session, user: User | None, shop_id: int) -> set[int]:
    if user is None:
        return set()
    rows = db.scalars(
        select(Favorite.product_id).where(Favorite.user_id == user.id, Favorite.shop_id == shop_id)
    ).all()
    return set(rows)


def is_favorite(db: Session, user: User | None, product_id: int) -> bool:
    if user is None:
        return False
    return (
        db.scalar(select(Favorite.id).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
        is not None
    )


def toggle_favorite(db: Session, user: User, share_code: str, product_id: int, shop_id: int) -> dict:
    from fastapi import HTTPException

    product = db.scalars(
        select(Product).where(Product.id == product_id, Product.shop_id == shop_id)
    ).one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="没有找到这个商品")
    existing = db.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id)
    )
    if existing is None:
        db.add(Favorite(user_id=user.id, shop_id=shop_id, product_id=product_id))
        db.commit()
        return {"favorited": True, "detail": "已加入收藏"}
    db.delete(existing)
    db.commit()
    return {"favorited": False, "detail": "已取消收藏"}


def _shop(db: Session, share_code: str) -> Shop:
    from app.services.catalog import shop_by_code

    return shop_by_code(db, share_code)


def favorite_products(db: Session, user: User, share_code: str) -> list[Product]:
    shop = _shop(db, share_code)
    rows = db.scalars(
        select(Favorite)
        .options(joinedload(Favorite.product).joinedload(Product.skus))
        .where(Favorite.user_id == user.id, Favorite.shop_id == shop.id)
        .order_by(Favorite.id.desc())
    ).unique().all()
    return [row.product for row in rows]


def _history_key(user_id: int, shop_id: int) -> str:
    return f"history:{user_id}:{shop_id}"


def record_view(user_id: int, shop_id: int, product_id: int) -> None:
    """最近看过的商品放最前，同一个商品只留一次。"""
    redis = get_redis()
    key = _history_key(user_id, shop_id)
    ids = redis.get_json(key) or []
    ids = [pid for pid in ids if pid != product_id]
    ids.insert(0, product_id)
    redis.set_json(key, ids[:HISTORY_LIMIT], ex=14 * 24 * 3600)


def history_products(db: Session, user: User, share_code: str) -> list[Product]:
    shop = _shop(db, share_code)
    ids = get_redis().get_json(_history_key(user.id, shop.id)) or []
    if not ids:
        return []
    rows = db.scalars(
        select(Product).options(joinedload(Product.skus)).where(Product.id.in_(ids), Product.shop_id == shop.id)
    ).unique().all()
    order = {pid: index for index, pid in enumerate(ids)}
    return sorted(rows, key=lambda product: order.get(product.id, 0))


def clear_history(user: User, share_code: str, shop_id: int) -> None:
    get_redis().delete_pattern(_history_key(user.id, shop_id))
