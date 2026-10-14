import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.redis_client import get_redis
from app.models.tables import Product, ProductTagLink, Shop, Sku, User
from app.schemas.dto import ProductIn, ProductUpdate, ShopUpdate, SkuIn, SkuUpdate
from app.services.reviews import rating_map
from app.services.shelf import listed_on_c, next_status, visible_skus
from app.services.tags import sync_product_tags, tags_of


def yuan(cents: int) -> float:
    return round(cents / 100, 2)


def to_cents(yuan_value: float) -> int:
    return int(round(yuan_value * 100))


def invalidate_catalog_cache() -> None:
    get_redis().delete_pattern("cache:c-products:*")


def merchant_shop(db: Session, user: User) -> Shop:
    shop = db.scalar(select(Shop).where(Shop.merchant_id == user.id))
    if shop is None:
        raise HTTPException(status_code=404, detail="还没有店铺")
    return shop


def shop_by_code(db: Session, share_code: str) -> Shop:
    shop = db.scalar(select(Shop).where(Shop.share_code == share_code))
    if shop is None:
        raise HTTPException(status_code=404, detail="没有找到这个店铺")
    return shop


def serialize_shop(shop: Shop) -> dict:
    return {
        "id": shop.id,
        "name": shop.name,
        "notice": shop.notice,
        "logo_url": shop.logo_url,
        "theme_color": shop.theme_color,
        "share_code": shop.share_code,
        "status": shop.status,
        "share_path": f"/c.html?code={shop.share_code}",
        "hero_height": shop.hero_height or 640,
        "strip_tint": bool(shop.strip_tint),
        "promises": promises_of(shop),
    }


# 商家没自己写售后保障时用这四条，和「满 99 包邮」的运费规则对上
DEFAULT_PROMISES = [
    {"title": "正品保障", "sub": "店主直发，假一赔十"},
    {"title": "7 天无理由", "sub": "定制品和已使用商品除外"},
    {"title": "满 99 包邮", "sub": "未满收 8 元运费"},
    {"title": "48 小时发货", "sub": "付款后按顺序发出"},
]


def promises_of(shop: Shop) -> list[dict]:
    raw = (shop.promises or "").strip()
    if not raw:
        return [dict(item) for item in DEFAULT_PROMISES]
    try:
        rows = json.loads(raw)
    except ValueError:
        return [dict(item) for item in DEFAULT_PROMISES]
    if not isinstance(rows, list) or not rows:
        return [dict(item) for item in DEFAULT_PROMISES]
    return [
        {"title": str(row.get("title", ""))[:16], "sub": str(row.get("sub", ""))[:40]}
        for row in rows
        if isinstance(row, dict) and str(row.get("title", "")).strip()
    ] or [dict(item) for item in DEFAULT_PROMISES]


def serialize_sku(sku: Sku, *, purchasable: bool | None = None) -> dict:
    data = {
        "id": sku.id,
        "spec": sku.spec,
        "image_url": sku.image_url or "",
        "price_yuan": yuan(sku.price_cents),
        "market_price_yuan": yuan(sku.market_price_cents) if sku.market_price_cents else None,
        "stock": sku.stock,
        "status": sku.status,
    }
    if purchasable is not None:
        data["purchasable"] = purchasable
    return data


def serialize_product(
    product: Product,
    *,
    audience: str,
    ratings: dict[int, tuple[float, int]] | None = None,
) -> dict:
    if audience == "c":
        skus = visible_skus(product)
        sku_rows = [serialize_sku(sku, purchasable=sku.stock > 0) for sku in skus]
    else:
        sku_rows = [serialize_sku(sku) for sku in product.skus]
    average, count = (ratings or {}).get(product.id, (None, 0))
    markets = [row["market_price_yuan"] for row in sku_rows if row.get("market_price_yuan")]
    tags = tags_of(product)
    return {
        "id": product.id,
        "shop_id": product.shop_id,
        "name": product.name,
        "category": product.category,
        "description": product.description,
        "image_url": product.image_url,
        "status": product.status,
        "sort_order": product.sort_order,
        "sales_count": product.sales_count,
        "limit_per_user": product.limit_per_user,
        "rating_avg": average,
        "review_count": count,
        "price_from": min((row["price_yuan"] for row in sku_rows), default=None),
        "market_from": min(markets, default=None),
        "tags": tags,
        "skus": sku_rows,
    }


def _product_query():
    return (
        select(Product)
        .options(
            joinedload(Product.skus),
            joinedload(Product.shop),
            # 卡片左上角的标签跟着商品一起取，避免每张卡片再查一次
            joinedload(Product.tag_links).joinedload(ProductTagLink.tag),
        )
        .order_by(Product.sort_order.asc(), Product.id.asc())
    )


def update_shop(db: Session, user: User, body: ShopUpdate) -> dict:
    shop = merchant_shop(db, user)
    if body.name is not None:
        shop.name = body.name.strip()
    if body.notice is not None:
        shop.notice = body.notice.strip()
    if body.logo_url is not None:
        shop.logo_url = body.logo_url.strip()
    if body.theme_color is not None:
        shop.theme_color = body.theme_color.lower()
    if body.hero_height is not None:
        shop.hero_height = body.hero_height
    if body.strip_tint is not None:
        shop.strip_tint = body.strip_tint
    if body.promises is not None:
        shop.promises = json.dumps(
            [{"title": row.title.strip(), "sub": row.sub.strip()} for row in body.promises],
            ensure_ascii=False,
        )
    if body.status is not None:
        shop.status = body.status
    db.commit()
    db.refresh(shop)
    invalidate_catalog_cache()
    return serialize_shop(shop)


def list_b_products(db: Session, user: User, keyword: str = "", status: str = "") -> list[dict]:
    shop = merchant_shop(db, user)
    products = db.scalars(_product_query().where(Product.shop_id == shop.id)).unique().all()
    if status in {"on", "off", "banned"}:
        products = [product for product in products if product.status == status]
    if keyword:
        products = [product for product in products if keyword in product.name]
    ratings = rating_map(db, [product.id for product in products])
    return [serialize_product(product, audience="b", ratings=ratings) for product in products]


def list_c_products(
    db: Session,
    share_code: str,
    keyword: str = "",
    category: str = "",
    sort: str = "default",
    user: User | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict]:
    shop = shop_by_code(db, share_code)
    if shop.status != "open":
        return []
    cache_key = f"cache:c-products:{shop.id}:{category or '-'}:{keyword or '-'}:{sort or 'default'}"
    cached = get_redis().get_json(cache_key)
    if cached is None:
        products = db.scalars(_product_query().where(Product.shop_id == shop.id)).unique().all()
        visible = [product for product in products if listed_on_c(product)]
        if category:
            visible = [product for product in visible if product.category == category]
        if keyword:
            visible = [product for product in visible if keyword in product.name or keyword in product.category]
        ratings = rating_map(db, [product.id for product in visible])
        data = [serialize_product(product, audience="c", ratings=ratings) for product in visible]
        if sort == "price_asc":
            data.sort(key=lambda item: item["price_from"] or 0)
        elif sort == "price_desc":
            data.sort(key=lambda item: item["price_from"] or 0, reverse=True)
        elif sort == "sales":
            data.sort(key=lambda item: item["sales_count"], reverse=True)
        get_redis().set_json(cache_key, data, ex=60)
        cached = data
    rows = list(cached)
    if limit is None:
        return rows[offset:] if offset else rows
    return rows[offset : offset + limit]


def list_categories(db: Session, share_code: str) -> list[str]:
    """买家端的分类标签，按商家在后台定的顺序返回。"""
    from app.services.categories import shop_category_names

    shop = shop_by_code(db, share_code)
    registered = shop_category_names(db, shop)
    if registered:
        used = {product["category"] for product in list_c_products(db, share_code)}
        return [name for name in registered if name in used] + [name for name in used if name and name not in registered]
    names: list[str] = []
    for product in list_c_products(db, share_code):
        if product["category"] and product["category"] not in names:
            names.append(product["category"])
    return names


def get_c_product(db: Session, share_code: str, product_id: int, user: User | None = None) -> dict:
    from fastapi import HTTPException

    shop = shop_by_code(db, share_code)
    product = db.scalars(_product_query().where(Product.id == product_id, Product.shop_id == shop.id)).unique().one_or_none()
    if product is None or not listed_on_c(product):
        raise HTTPException(status_code=404, detail="没有找到这个商品")
    ratings = rating_map(db, [product.id])
    return serialize_product(product, audience="c", ratings=ratings)


def dashboard(db: Session, user: User) -> dict:
    from app.models.tables import Order

    shop = merchant_shop(db, user)
    products = db.scalars(select(Product).where(Product.shop_id == shop.id)).all()
    orders = db.scalars(select(Order).where(Order.shop_id == shop.id)).all()
    sold = [order for order in orders if order.status in {"paid", "shipped", "completed"}]
    low = [
        {"product_name": sku.product.name, "spec": sku.spec, "stock": sku.stock}
        for product in products
        for sku in product.skus
        if sku.status == "on" and sku.stock <= 5
    ]
    recent = [
        {
            "order_no": order.order_no,
            "status": order.status,
            "total_yuan": yuan(order.total_cents),
            "buyer": order.buyer.nickname if order.buyer is not None else "",
        }
        for order in sorted(orders, key=lambda item: item.id, reverse=True)[:5]
    ]
    return {
        "product_total": len(products),
        "on_sale": sum(1 for product in products if product.status == "on"),
        "off_shelf": sum(1 for product in products if product.status == "off"),
        "banned": sum(1 for product in products if product.status == "banned"),
        "pending_pay": sum(1 for order in orders if order.status == "pending"),
        "pending_ship": sum(1 for order in orders if order.status == "paid"),
        "shipped": sum(1 for order in orders if order.status == "shipped"),
        "sales_yuan": yuan(sum(order.total_cents for order in sold)),
        "low_stock": low,
        "recent_orders": recent,
    }


def _owned_product(db: Session, user: User, product_id: int) -> Product:
    shop = merchant_shop(db, user)
    product = db.scalars(_product_query().where(Product.id == product_id, Product.shop_id == shop.id)).unique().one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="没有找到这个商品")
    return product


def _sku_row(sku: SkuIn) -> Sku:
    return Sku(
        spec=sku.spec.strip(),
        image_url=sku.image_url.strip(),
        price_cents=to_cents(sku.price_yuan),
        market_price_cents=to_cents(sku.market_price_yuan) if sku.market_price_yuan else 0,
        stock=sku.stock,
        status="on",
    )


def create_product(db: Session, user: User, body: ProductIn) -> dict:
    shop = merchant_shop(db, user)
    max_sort = db.scalar(select(func.max(Product.sort_order)).where(Product.shop_id == shop.id)) or 0
    product = Product(
        shop_id=shop.id,
        name=body.name.strip(),
        category=body.category.strip(),
        description=body.description.strip(),
        image_url=body.image_url.strip(),
        status="off",
        sort_order=max_sort + 1,
        limit_per_user=body.limit_per_user,
    )
    for sku in body.skus:
        product.skus.append(_sku_row(sku))
    db.add(product)
    db.commit()
    from app.services.categories import register_category_name

    register_category_name(db, shop.id, product.category)
    sync_product_tags(db, product, body.tag_names)
    db.commit()
    saved = _owned_product(db, user, product.id)
    invalidate_catalog_cache()
    return serialize_product(saved, audience="b")


def add_sku(db: Session, user: User, product_id: int, body: SkuIn) -> dict:
    product = _owned_product(db, user, product_id)
    spec = body.spec.strip()
    if any(sku.spec == spec for sku in product.skus):
        raise HTTPException(status_code=400, detail="这个规格已经存在")
    product.skus.append(_sku_row(body))
    db.commit()
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, product_id), audience="b")


def update_product(db: Session, user: User, product_id: int, body: ProductUpdate) -> dict:
    product = _owned_product(db, user, product_id)
    if body.name is not None:
        product.name = body.name.strip()
    if body.category is not None:
        product.category = body.category.strip()
    if body.description is not None:
        product.description = body.description.strip()
    if body.image_url is not None:
        product.image_url = body.image_url.strip()
    if body.sort_order is not None:
        product.sort_order = body.sort_order
    if body.limit_per_user is not None:
        product.limit_per_user = body.limit_per_user
    if body.tag_names is not None:
        sync_product_tags(db, product, body.tag_names)
    db.commit()
    if body.category is not None:
        from app.services.categories import register_category_name

        register_category_name(db, product.shop_id, product.category)
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, product_id), audience="b")


def change_product_status(db: Session, user: User, product_id: int, action: str) -> dict:
    product = _owned_product(db, user, product_id)
    product.status = next_status(product.status, action)
    db.commit()
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, product_id), audience="b")


def _owned_sku(db: Session, user: User, sku_id: int) -> Sku:
    shop = merchant_shop(db, user)
    sku = db.scalar(
        select(Sku)
        .join(Product)
        .options(joinedload(Sku.product).joinedload(Product.shop))
        .where(Sku.id == sku_id, Product.shop_id == shop.id)
    )
    if sku is None:
        raise HTTPException(status_code=404, detail="没有找到这个 SKU")
    return sku


def update_sku(db: Session, user: User, sku_id: int, body: SkuUpdate) -> dict:
    sku = _owned_sku(db, user, sku_id)
    if body.spec is not None:
        sku.spec = body.spec.strip()
    if body.image_url is not None:
        sku.image_url = body.image_url.strip()
    if body.price_yuan is not None:
        sku.price_cents = to_cents(body.price_yuan)
    if body.market_price_yuan is not None:
        sku.market_price_cents = to_cents(body.market_price_yuan)
    if body.stock is not None:
        sku.stock = body.stock
    db.commit()
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, sku.product_id), audience="b")


def change_sku_status(db: Session, user: User, sku_id: int, action: str) -> dict:
    sku = _owned_sku(db, user, sku_id)
    sku.status = next_status(sku.status, action)
    db.commit()
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, sku.product_id), audience="b")


def load_sku_for_shop(db: Session, shop_id: int, sku_id: int) -> Sku | None:
    return db.scalar(
        select(Sku)
        .join(Product)
        .options(joinedload(Sku.product).joinedload(Product.shop))
        .where(Sku.id == sku_id, Product.shop_id == shop_id)
    )


def search_on_sale(db: Session, shop_id: int, keyword: str, limit: int = 5) -> str:
    products = db.scalars(_product_query().where(Product.shop_id == shop_id).limit(limit * 4)).unique().all()
    word = keyword.strip()
    lines = []
    for product in products:
        if not listed_on_c(product):
            continue
        if word not in product.name and word not in product.category:
            continue
        sku_text = "；".join(
            f"{sku.spec} ¥{yuan(sku.price_cents):.2f} 库存{sku.stock}" for sku in visible_skus(product)
        )
        lines.append(f"{product.name}（商品id {product.id}，{product.category}）：{sku_text}")
    if not lines:
        return f"没有找到在售商品：{keyword}"
    return "在售商品：\n" + "\n".join(lines)


def describe_inventory(db: Session, shop_id: int, sku_id: int) -> str:
    sku = load_sku_for_shop(db, shop_id, sku_id)
    if sku is None or sku.status != "on" or sku.product.status != "on" or sku.product.shop.status != "open":
        return "没有找到可售的 SKU。"
    return f"{sku.product.name} / {sku.spec} 库存 {sku.stock}，单价 ¥{yuan(sku.price_cents):.2f}"
