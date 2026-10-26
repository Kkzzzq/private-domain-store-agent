"""C 端投影：把 SPU/SKU 权威表加工成买家端宽表，读路径只认这张表。

分工必须说清：
- 商家端 B、平台端 OP 直接读写 products / skus，拿到的是实时权威值；
- 买家端 C 只读 c_product_views，一次查询拿全卡片与规格明细，不做 join；
- 交易（下单、支付、扣库存）仍然回查权威表，投影不承担资金与库存正确性。

投影是派生数据，所以有三道同步：写路径显式刷新、读路径按指纹自愈、
进程启动时整表重建。草稿状态不投影，因此买家端不可能读到草稿。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.tables import CProductView, Product, ProductTagLink, Sku, utcnow

DRAFT = "draft"


def yuan(cents: int | None) -> float | None:
    return None if cents is None else round(cents / 100, 2)


def _stamp(value: datetime | None) -> str:
    # MySQL DATETIME 默认只到秒，指纹统一按秒取，避免读回后精度不同导致永久判脏
    return value.strftime("%Y%m%d%H%M%S") if value else ""


def spu_content(
    *,
    spu_no: str | None,
    name: str | None,
    category: str | None,
    description: str | None,
    image_url: str | None,
    sort_order: int | None,
    sales_count: int | None,
    limit_per_user: int | None,
) -> str:
    """SPU 上所有会被投影复制的展示字段，压成一个可比较的串。"""
    return "|".join(
        [
            spu_no or "",
            name or "",
            category or "",
            description or "",
            image_url or "",
            str(sort_order or 0),
            str(sales_count or 0),
            str(limit_per_user or 0),
        ]
    )


def product_fingerprint(
    *,
    status: str | None,
    product_updated_at: datetime | None,
    content: str,
    sku_count: int,
    stock_sum: int,
    price_sum: int,
    price_max: int,
    sku_updated_max: datetime | None,
    sku_content: str,
) -> str:
    """投影版本指纹。

    只信时间戳不够：时间戳在 MySQL 上只到秒，同一秒里改价改名就看不出来。
    所以把 SPU 展示字段、状态、规格数、库存合计、价格合计与最高价一起压进指纹，
    同时比较完整 SKU 展示字段，覆盖同秒状态、图片、参数变更及合计不变的库存调换。分类改名、排序调整这类批量 UPDATE 也走这里，
    因为它们不会保证把 updated_at 推到下一秒。
    """
    parts = [
        status or "",
        _stamp(product_updated_at),
        content,
        str(sku_count),
        str(stock_sum),
        str(price_sum),
        str(price_max),
        _stamp(sku_updated_max),
        sku_content,
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:32]


def _sku_content(skus) -> str:
    # 比较完整规格内容，不能用合计代替：两个规格互换库存/价格时合计不变。
    return json.dumps([_sku_payload(sku) for sku in sorted(skus, key=_order_key)],
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint_from_skus(product: Product) -> tuple[int, int, int, int, datetime | None]:
    skus = list(product.skus)
    return (
        len(skus),
        sum(sku.stock or 0 for sku in skus),
        sum(sku.price_cents or 0 for sku in skus),
        max((sku.price_cents or 0 for sku in skus), default=0),
        max((sku.updated_at for sku in skus if sku.updated_at), default=None),
    )


def _order_key(sku: Sku) -> tuple[int, int]:
    return (sku.sort_order or 0, sku.id or 0)


def _sku_payload(sku: Sku) -> dict:
    return {
        "id": sku.id,
        "sort_order": sku.sort_order or 0,
        "spec": sku.spec,
        "image_url": sku.image_url or "",
        "parameters": sku.parameter_profile.parameters if sku.parameter_profile else [],
        "price_yuan": yuan(sku.price_cents),
        "market_price_yuan": yuan(sku.market_price_cents) if sku.market_price_cents else None,
        "stock": sku.stock,
        "status": sku.status,
    }


def build_payload(
    product: Product,
    *,
    rating: tuple[float | None, int] = (None, 0),
    tags: list[dict] | None = None,
    shop_name: str = "",
    shop_share_code: str = "",
) -> dict:
    """一个 SPU 的完整展示载荷。规格保留全量（含已下架规格），读取方按场景过滤。"""
    skus = sorted(product.skus, key=_order_key)
    sku_rows = [_sku_payload(sku) for sku in skus]
    visible = [row for row in sku_rows if row["status"] == "on"]
    starting = min(visible, key=lambda row: (row["price_yuan"], row["id"]), default=None)
    average, count = rating
    return {
        "id": product.id,
        "spu_id": product.spu_id,
        "shop_id": product.shop_id,
        "shop_name": shop_name,
        "shop_share_code": shop_share_code,
        "name": product.name,
        "category": product.category,
        "description": product.description,
        "image_url": product.image_url,
        "status": product.status,
        "sort_order": product.sort_order or 0,
        "sales_count": product.sales_count or 0,
        "limit_per_user": product.limit_per_user or 0,
        "rating_avg": average,
        "review_count": count,
        "price_from": min((row["price_yuan"] for row in visible), default=None),
        "market_from": starting["market_price_yuan"] if starting else None,
        "tags": list(tags or []),
        "skus": sku_rows,
    }


def _rating(db: Session, product_id: int) -> tuple[float | None, int]:
    from app.services.reviews import rating_map

    return rating_map(db, [product_id]).get(product_id, (None, 0))


def _tags(product: Product) -> list[dict]:
    from app.services.tags import tags_of

    return tags_of(product)


def _shop_labels(db: Session, shop_id: int) -> tuple[str, str]:
    from app.models.tables import Shop

    shop = db.get(Shop, shop_id)
    return (shop.name, shop.share_code) if shop else ("", "")


def refresh_product(db: Session, product_id: int, *, commit: bool = True) -> CProductView | None:
    """按权威表重建一个 SPU 的投影。草稿会顺手清掉已有投影。"""
    product = db.scalars(
        select(Product)
        .options(
            joinedload(Product.skus).joinedload(Sku.parameter_profile),
            joinedload(Product.tag_links).joinedload(ProductTagLink.tag),
        )
        .where(Product.id == product_id)
    ).unique().one_or_none()
    view = db.get(CProductView, product_id)
    if product is None or product.status == DRAFT:
        if view is not None:
            db.delete(view)
            if commit:
                db.commit()
        return None

    sku_count, stock_sum, price_sum, price_max, sku_updated = _fingerprint_from_skus(product)
    fingerprint = product_fingerprint(
        status=product.status,
        product_updated_at=product.updated_at,
        content=spu_content(
            spu_no=product.spu_id,
            name=product.name,
            category=product.category,
            description=product.description,
            image_url=product.image_url,
            sort_order=product.sort_order,
            sales_count=product.sales_count,
            limit_per_user=product.limit_per_user,
        ),
        sku_count=sku_count,
        stock_sum=stock_sum,
        price_sum=price_sum,
        price_max=price_max,
        sku_updated_max=sku_updated,
        sku_content=_sku_content(product.skus),
    )
    shop_name, share_code = _shop_labels(db, product.shop_id)
    payload = build_payload(
        product,
        rating=_rating(db, product.id),
        tags=_tags(product),
        shop_name=shop_name,
        shop_share_code=share_code,
    )
    listed = product.status == "on" and any(row["status"] == "on" for row in payload["skus"])
    price_from = payload["price_from"]
    values = {
        "spu_id": product.id,
        "shop_id": product.shop_id,
        "spu_no": product.spu_id,
        "status": product.status,
        "listed": listed,
        "name": product.name,
        "category": product.category,
        "sort_order": product.sort_order or 0,
        "sales_count": product.sales_count or 0,
        "price_from_cents": int(round(price_from * 100)) if price_from is not None else None,
        "payload": payload,
        "source_version": fingerprint,
        "updated_at": utcnow(),
    }
    if view is None:
        view = CProductView(**values)
        db.add(view)
    else:
        for key, value in values.items():
            setattr(view, key, value)
    if commit:
        db.commit()
    return view


def refresh_shop(db: Session, shop_id: int, *, commit: bool = True) -> int:
    """整店重建，用于种子数据、迁移和批量写操作。"""
    ids = list(db.scalars(select(Product.id).where(Product.shop_id == shop_id)))
    for product_id in ids:
        refresh_product(db, product_id, commit=False)
    orphans = [row for row in db.scalars(select(CProductView).where(CProductView.shop_id == shop_id)) if row.spu_id not in ids]
    for row in orphans:
        db.delete(row)
    if commit:
        db.commit()
    return len(ids)


def rebuild_all(db: Session, *, commit: bool = True) -> int:
    shop_ids = list(db.scalars(select(Product.shop_id).distinct()))
    for shop_id in shop_ids:
        refresh_shop(db, shop_id, commit=False)
    stale = [row for row in db.scalars(select(CProductView)) if row.shop_id not in set(shop_ids)]
    for row in stale:
        db.delete(row)
    if commit:
        db.commit()
    return len(shop_ids)


def _fingerprints(db: Session, shop_id: int) -> dict[int, tuple[str, str]]:
    rows = db.execute(
        select(
            Product.id,
            Product.spu_id,
            Product.name,
            Product.category,
            Product.description,
            Product.image_url,
            Product.sort_order,
            Product.sales_count,
            Product.limit_per_user,
            Product.status,
            Product.updated_at,
            func.count(Sku.id),
            func.coalesce(func.sum(Sku.stock), 0),
            func.coalesce(func.sum(Sku.price_cents), 0),
            func.coalesce(func.max(Sku.price_cents), 0),
            func.max(Sku.updated_at),
        )
        .outerjoin(Sku, Sku.spu_id == Product.id)
        .where(Product.shop_id == shop_id)
        .group_by(Product.id)
    ).all()
    sku_groups: dict[int, list[Sku]] = {}
    for sku in db.scalars(select(Sku).join(Product, Product.id == Sku.spu_id)
                          .options(joinedload(Sku.parameter_profile))
                          .where(Product.shop_id == shop_id)).unique():
        sku_groups.setdefault(sku.spu_id, []).append(sku)
    fingerprints: dict[int, tuple[str, str]] = {}
    for row in rows:
        fingerprints[int(row.id)] = (
            row.status,
            product_fingerprint(
                status=row.status,
                product_updated_at=row.updated_at,
                content=spu_content(
                    spu_no=row.spu_id,
                    name=row.name,
                    category=row.category,
                    description=row.description,
                    image_url=row.image_url,
                    sort_order=row.sort_order,
                    sales_count=row.sales_count,
                    limit_per_user=row.limit_per_user,
                ),
                sku_count=int(row[11] or 0),
                stock_sum=int(row[12] or 0),
                price_sum=int(row[13] or 0),
                price_max=int(row[14] or 0),
                sku_updated_max=row[15],
                sku_content=_sku_content(sku_groups.get(int(row.id), [])),
            ),
        )
    return fingerprints


def sync_shop(db: Session, shop_id: int) -> None:
    """读时自愈：指纹对不上就重建那一个 SPU，保证 B 端改完 C 端立刻正确。

    比较 SPU 展示字段与完整 SKU 内容；标签与评价由写入口显式刷新。
    """
    truth = _fingerprints(db, shop_id)
    views = {row.spu_id: row for row in db.scalars(select(CProductView).where(CProductView.shop_id == shop_id))}
    dirty: list[int] = []
    for product_id, (status, fingerprint) in truth.items():
        view = views.get(product_id)
        if status == DRAFT:
            if view is not None:
                dirty.append(product_id)
            continue
        if view is None or view.source_version != fingerprint:
            dirty.append(product_id)
    for product_id in [pid for pid in views if pid not in truth]:
        dirty.append(product_id)
    if not dirty:
        return
    for product_id in dirty:
        refresh_product(db, product_id, commit=False)
    db.commit()
    from app.services.catalog import invalidate_catalog_cache
    invalidate_catalog_cache()


# ---------- 读取 ----------
def view_rows(
    db: Session,
    shop_id: int,
    *,
    keyword: str = "",
    category: str = "",
    sort: str = "default",
    listed_only: bool = True,
) -> list[CProductView]:
    query = select(CProductView).where(CProductView.shop_id == shop_id)
    if listed_only:
        query = query.where(CProductView.listed.is_(True))
    if category:
        query = query.where(CProductView.category == category)
    if keyword:
        word = keyword.strip()
        query = query.where(CProductView.name.like(f"%{word}%") | CProductView.category.like(f"%{word}%"))
    if sort == "price_asc":
        query = query.order_by(CProductView.price_from_cents.asc())
    elif sort == "price_desc":
        query = query.order_by(CProductView.price_from_cents.desc())
    elif sort == "sales":
        query = query.order_by(CProductView.sales_count.desc())
    else:
        query = query.order_by(CProductView.sort_order.asc(), CProductView.spu_id.asc())
    return list(db.scalars(query))


def view_row(db: Session, shop_id: int, spu_id: int) -> CProductView | None:
    return db.scalar(
        select(CProductView).where(
            CProductView.shop_id == shop_id,
            CProductView.spu_id == spu_id,
            CProductView.listed.is_(True),
        )
    )


def listed_categories(db: Session, shop_id: int) -> list[str]:
    rows = db.execute(
        select(CProductView.category, func.count(CProductView.spu_id))
        .where(CProductView.shop_id == shop_id, CProductView.listed.is_(True))
        .group_by(CProductView.category)
    ).all()
    return [category for category, _ in rows if category]


def serialize_c(view: CProductView, *, preserve_skus: set[int] | None = None) -> dict:
    """买家端商品卡片 / 详情。规格只留上架中的，并可再按调用方给的 SKU 集合收窄。"""
    payload = dict(view.payload)
    skus = []
    for row in payload.get("skus", []):
        if row.get("status") != "on":
            continue
        if preserve_skus is not None and row["id"] not in preserve_skus:
            continue
        skus.append({**row, "purchasable": row.get("stock", 0) > 0})
    starting = min(skus, key=lambda row: (row["price_yuan"], row["id"]), default=None)
    payload["skus"] = skus
    payload["price_from"] = min((row["price_yuan"] for row in skus), default=None)
    payload["market_from"] = starting["market_price_yuan"] if starting else None
    payload.pop("shop_name", None)
    payload.pop("shop_share_code", None)
    return payload


def serialize_saved(view: CProductView, *, shop_open: bool) -> dict:
    """浏览记录：下架、禁售的商品也保留名称与价格，只是不可购买。"""
    payload = dict(view.payload)
    available = bool(shop_open and view.listed)
    label = "在售"
    if payload.get("status") == "banned":
        label = "已禁售"
    elif payload.get("status") == "off":
        label = "已下架"
    elif not shop_open:
        label = "店铺停业"
    skus = [
        {**row, "purchasable": bool(available and row.get("status") == "on" and row.get("stock", 0) > 0)}
        for row in payload.get("skus", [])
    ]
    markets = [row["market_price_yuan"] for row in skus if row.get("market_price_yuan")]
    payload["skus"] = skus
    payload["available"] = available
    payload["shelf_label"] = label
    payload["price_from"] = min((row["price_yuan"] for row in skus if row.get("status") == "on"), default=None)
    payload["market_from"] = min(markets, default=None)
    return payload


def purge_views(db: Session, product_id: int, *, commit: bool = True) -> None:
    db.execute(delete(CProductView).where(CProductView.spu_id == product_id))
    if commit:
        db.commit()