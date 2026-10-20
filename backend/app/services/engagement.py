from app.services.governance import shop_open, shop_blocked
"""买家的浏览历史。

历史放 Redis，不落库：只保留最近 7 天看过的商品，不分店铺，
在哪家店看过的都进同一个列表。下架或禁售的商品仍然留在列表里，只是带上标注。
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.redis_client import get_redis
from app.models.tables import Product, User
from app.services.shelf import listed_on_c

HISTORY_DAYS = 7
HISTORY_LIMIT = 60
HISTORY_TTL = HISTORY_DAYS * 24 * 3600


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
    """给浏览记录用的状态标注。"""
    if product.status == "banned":
        return "已禁售"
    if product.status == "off":
        return "已下架"
    if product.shop is not None and not shop_open(product.shop):
        return "店铺停业"
    return "在售"


def serialize_saved(product: Product, *, ratings: dict | None = None) -> dict:
    """浏览记录列表用。下架的商品也要能看到名称和价格，所以规格不过滤状态。"""
    from app.services.catalog import yuan

    available = listed_on_c(product)
    sku_rows = [
        {
            "id": sku.id,
            "spec": sku.spec,
            "image_url": sku.image_url or "",
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
        "price_from": min((row["price_yuan"] for row in sku_rows), default=None),
        "market_from": min(markets, default=None),
        "skus": sku_rows,
    }


def serialize_saved_list(db: Session, user: User, products: list[Product]) -> list[dict]:
    from app.services.reviews import rating_map

    ratings = rating_map(db, [product.id for product in products])
    return [serialize_saved(product, ratings=ratings) for product in products]
