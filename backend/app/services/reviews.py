"""商品评价。只有确认收货的订单明细才能评一次。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.tables import Order, OrderItem, Product, Review, User
from app.schemas.dto import ReviewIn


def rating_map(db: Session, product_ids: list[int]) -> dict[int, tuple[float, int]]:
    if not product_ids:
        return {}
    rows = db.execute(
        select(Review.product_id, func.avg(Review.rating), func.count(Review.id))
        .where(Review.product_id.in_(product_ids))
        .group_by(Review.product_id)
    ).all()
    return {pid: (round(float(avg), 1), int(count)) for pid, avg, count in rows}


def list_reviews(db: Session, product_id: int, limit: int = 20) -> list[dict]:
    rows = db.scalars(
        select(Review)
        .options(joinedload(Review.user))
        .where(Review.product_id == product_id)
        .order_by(Review.id.desc())
        .limit(limit)
    ).unique().all()
    return [
        {
            "id": row.id,
            "product_id": row.product_id,
            "product_name": "",
            "rating": row.rating,
            "content": row.content,
            "nickname": _mask(row.user.nickname or row.user.username) if row.user else "买家",
            "created_at": row.created_at.strftime("%Y-%m-%d") if row.created_at else "",
        }
        for row in rows
    ]


def _mask(name: str) -> str:
    if len(name) <= 1:
        return name
    return name[0] + "*" * (len(name) - 1)


def pending_reviews(db: Session, user: User) -> list[dict]:
    """已完成订单里还没评价的明细。"""
    rows = db.scalars(
        select(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .options(joinedload(OrderItem.product), joinedload(OrderItem.sku))
        .where(Order.user_id == user.id, Order.status == "completed")
        .order_by(OrderItem.id.desc())
    ).unique().all()
    reviewed = set(db.scalars(select(Review.order_item_id)).all())
    pending = []
    for item in rows:
        if item.id in reviewed:
            continue
        order = db.scalar(select(Order.order_no).where(Order.id == item.order_id))
        pending.append(
            {
                "order_item_id": item.id,
                "order_no": order or "",
                "product_id": item.product_id,
                "product_name": item.product_name,
                "sku_spec": item.sku_spec,
            }
        )
    return pending


def create_review(db: Session, user: User, body: ReviewIn) -> dict:
    from fastapi import HTTPException

    item = db.scalars(
        select(OrderItem)
        .options(joinedload(OrderItem.order))
        .where(OrderItem.id == body.order_item_id, OrderItem.order.has(user_id=user.id))
    ).unique().one_or_none()
    if item is None or item.order is None or item.order.status != "completed":
        raise HTTPException(status_code=400, detail="只能评价已完成订单里的商品")
    exists = db.scalar(select(Review.id).where(Review.order_item_id == item.id))
    if exists is not None:
        raise HTTPException(status_code=409, detail="这条商品已经评价过了")
    review = Review(
        user_id=user.id,
        product_id=item.product_id,
        order_item_id=item.id,
        rating=body.rating,
        content=body.content.strip(),
    )
    db.add(review)
    db.commit()
    from app.services.catalog import invalidate_catalog_cache
    invalidate_catalog_cache()
    db.refresh(review)
    return {
        "id": review.id,
        "product_id": review.product_id,
        "product_name": item.product_name,
        "rating": review.rating,
        "content": review.content,
        "nickname": _mask(user.nickname or user.username),
        "created_at": review.created_at.strftime("%Y-%m-%d"),
    }
