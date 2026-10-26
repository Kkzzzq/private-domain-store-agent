"""买家的浏览历史。

历史放 Redis，不落库：只保留最近 7 天看过的商品，不分店铺，
在哪家店看过的都进同一个列表。下架或禁售的商品仍然留在列表里，只是带上标注。
列表内容取自 C 端宽表，所以展示口径与商品卡片完全一致。
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.redis_client import get_redis
from app.models.tables import CProductView, Shop, User
from app.services.c_projection import serialize_saved
from app.services.governance import shop_open

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


def history_views(db: Session, user: User) -> list[CProductView]:
    """浏览记录里的商品来自 C 端宽表；已删除的商品自然不再出现。"""
    ids = _recent_ids(user.id)
    if not ids:
        return []
    from app.services.c_projection import sync_shop
    shop_ids = set(db.scalars(select(CProductView.shop_id).where(CProductView.spu_id.in_(ids))))
    for shop_id in shop_ids:
        sync_shop(db, shop_id)
    rows = db.scalars(select(CProductView).where(CProductView.spu_id.in_(ids))).all()
    by_id = {row.spu_id: row for row in rows}
    return [by_id[product_id] for product_id in ids if product_id in by_id]


def clear_history(user: User) -> None:
    get_redis().delete_pattern(_history_key(user.id))


# ---------- 序列化 ----------
def serialize_saved_list(db: Session, user: User, views: list[CProductView]) -> list[dict]:
    """营业状态每次现查，店铺被冻结后浏览记录立刻标注停业。"""
    shop_ids = {view.shop_id for view in views}
    shops = {row.id: row for row in db.scalars(select(Shop).where(Shop.id.in_(shop_ids)))} if shop_ids else {}
    return [
        serialize_saved(view, shop_open=shop_open(shops[view.shop_id]) if view.shop_id in shops else False)
        for view in views
    ]
