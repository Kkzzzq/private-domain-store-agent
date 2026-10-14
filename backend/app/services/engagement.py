"""买家侧的收藏和浏览历史。

收藏落库，浏览历史放 Redis。两边都不分店铺，买家在哪家店点的心和看过的商品，
进的都是同一个列表。下架或禁售的商品仍然留在列表里，只是带上标注。
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.redis_client import get_redis
from app.models.tables import Favorite, Product, User
from app.services.shelf import listed_on_c

HISTORY_DAYS = 7
HISTORY_LIMIT = 60
HISTORY_TTL = HISTORY_DAYS * 24 * 3600


# ---------- 收藏 ----------
def favorite_ids(db: Session, user: User | None) -> set[int]:
    """当前用户收藏过的商品 id。不分店铺。"""
    if user is None or user.role != "customer":
        return set()
    rows = db.scalars(select(Favorite.product_id).where(Favorite.user_id == user.id)).all()
    return set(rows)


def is_favorite(db: Session, user: User | None, product_id: int) -> bool:
    if user is None or user.role != "customer":
        return False
    return (
        db.scalar(select(Favorite.id).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
        is not None
    )


def toggle_favorite(db: Session, user: User, product_id: int) -> dict:
    from fastapi import HTTPException

    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="没有找到这个商品")
    existing = db.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id)
    )
    if existing is None:
        db.add(Favorite(user_id=user.id, shop_id=product.shop_id, product_id=product_id))
        db.commit()
        return {"favorited": True, "detail": "已加入收藏"}
    db.delete(existing)
    db.commit()
    return {"favorited": False, "detail": "已取消收藏"}


def favorite_products(db: Session, user: User) -> list[Product]:
    rows = db.scalars(
        select(Favorite)
        .options(
            joinedload(Favorite.product).joinedload(Product.skus),
            joinedload(Favorite.product).joinedload(Product.shop),
        )
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.id.desc())
    ).unique().all()
    return [row.product for row in rows if row.product is not None]


# ---------- 浏览记录 ----------
def _history_key(user_id: int) -> str:
    return f"history:{user_id}"


def record_view(user_id: int, product_id: int) -> None:
    """最近看过的放最前，同一个商品只留一条，并更新它的时间。"""
    redis = get_redis()
    key = _history_key(user_id)
    rows = redis.get_json(key) or []
    now = int(time.time())
    kept = [row for row in rows if isinstance(row, dict) and row.get("id") != product_id]
    kept.insert(0, {"id": product_id, "at": now})
    redis.set_json(key, kept[:HISTORY_LIMIT], ex=HISTORY_TTL)


def _recent_ids(user_id: int) -> list[int]:
    """只取最近 7 天看过的，按时间倒序。"""
    rows = get_redis().get_json(_history_key(user_id)) or []
    cutoff = int(time.time()) - HISTORY_TTL
    ids: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if int(row.get("at") or 0) < cutoff:
            continue
        if row.get("id") not in ids:
            ids.append(row["id"])
    return ids


def history_products(db: Session, user: User) -> list[Product]:
    ids = _recent_ids(user.id)
    if not ids:
        return []
    rows = db.scalars(
        select(Product)
        .options(joinedload(Product.skus), joinedload(Product.shop))
        .where(Product.id.in_(ids))
    ).unique().all()
    order = {pid: index for index, pid in enumerate(ids)}
    return sorted(rows, key=lambda product: order.get(product.id, 0))


def clear_history(user: User) -> None:
    get_redis().delete_pattern(_history_key(user.id))


# ---------- 序列化 ----------
def shelf_label(product: Product) -> str:
    """给收藏和浏览记录用的状态标注。"""
    if product.status == "banned":
        return "已禁售"
    if product.status == "off":
        return "已下架"
    if product.shop is not None and product.shop.status != "open":
        return "店铺停业"
    return "在售"


def serialize_saved(product: Product, *, ratings: dict | None = None, favorites: set[int] | None = None) -> dict:
    """收藏/历史列表用。下架的商品也要能看到名称和价格，所以规格不过滤状态。"""
    from app.services.catalog import yuan

    available = listed_on_c(product)
    sku_rows = [
        {
            "id": sku.id,
            "spec": sku.spec,
            "price_yuan": yuan(sku.price_cents),
            "market_price_yuan": yuan(sku.market_price_cents) if sku.market_price_cents else None,
            "stock": sku.stock,
            "status": sku.status,
            # 只有还在售且这家店营业时才能直接加购
            "purchasable": bool(available and sku.status == "on" and sku.stock > 0),
        }
        for sku in product.skus
    ]
    markets = [row["market_price_yuan"] for row in sku_rows if row["market_price_yuan"]]
    average, count = (ratings or {}).get(product.id, (None, 0))
    return {
        "id": product.id,
        "shop_id": product.shop_id,
        "shop_name": product.shop.name if product.shop is not None else "",
        "shop_share_code": product.shop.share_code if product.shop is not None else "",
        "name": product.name,
        "category": product.category,
        "description": product.description,
        "image_url": product.image_url,
        "status": product.status,
        "shelf_label": shelf_label(product),
        "available": available,
        "sort_order": product.sort_order,
        "sales_count": product.sales_count,
        "limit_per_user": product.limit_per_user,
        "rating_avg": average,
        "review_count": count,
        "favorited": product.id in (favorites or set()),
        "price_from": min((row["price_yuan"] for row in sku_rows), default=None),
        "market_from": min(markets, default=None),
        "skus": sku_rows,
    }


def serialize_saved_list(db: Session, user: User, products: list[Product]) -> list[dict]:
    from app.services.reviews import rating_map

    ratings = rating_map(db, [product.id for product in products])
    favorites = favorite_ids(db, user)
    return [serialize_saved(product, ratings=ratings, favorites=favorites) for product in products]
