import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.redis_client import get_redis
from app.models.tables import Product, ProductTagLink, Shop, ShopAssistantProfile, Sku, SkuParameterProfile, User
from app.services.assistant_identity import assistant_name
from app.schemas.dto import ProductIn, ProductUpdate, ShopUpdate, SkuIn, SkuUpdate
from app.services.c_projection import (
    listed_categories,
    refresh_product,
    refresh_shop,
    serialize_c,
    sync_shop,
    view_row,
    view_rows,
)
from app.services.reviews import rating_map
from app.services.shelf import assert_merchant_editable, next_status, ordered_skus, visible_skus
from app.services.tags import sync_product_tags, tags_of
from app.services.governance import shop_open, shop_blocked


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
    from app.services.storefront import storefront_settings
    return {
        "storefront": storefront_settings(shop).model_dump(),
        "assistant_name": assistant_name(shop),
        "id": shop.id,
        "name": shop.name,
        "notice": shop.notice,
        "logo_url": shop.logo_url,
        "theme_color": shop.theme_color,
        "share_code": shop.share_code,
        "status": "open" if shop_open(shop) else "closed",
        "business_status": shop.status,
        "platform_blocked": shop_blocked(shop),
        "share_path": f"/c.html?code={shop.share_code}",
        "hero_height": shop.hero_height or 640,
        "strip_tint": bool(shop.strip_tint),
        "promises": promises_of(shop),
        "social_accounts": json.loads(shop.social_accounts or "[]"),
    }


# 商家没自己写售后保障时用这四条，和「满 99 包邮」的运费规则对上
DEFAULT_PROMISES = [
    {"title": "正品保障", "sub": "店主直发，假一赔十"},
    {"title": "7 天无理由", "sub": "定制品和已使用商品除外"},
    {"title": "满 99 包邮", "sub": "未满收 8 元运费"},
    {"title": "48 小时发货", "sub": "付款后按顺序发出"},
]


def _configured_promises(settings):
    from app.services.storefront import shipping_promise
    return {
        "authenticity": dict(DEFAULT_PROMISES[0]),
        "returns": dict(DEFAULT_PROMISES[1]) if settings.return_text == "7天无理由退货，定制品和已使用商品除外" else
                   {"title": "退换说明", "sub": settings.return_text[:40]} if settings.return_text else None,
        "shipping": shipping_promise(settings),
        "dispatch": dict(DEFAULT_PROMISES[3]) if settings.dispatch_text == "付款后48小时内发货" else
                    {"title": "发货说明", "sub": settings.dispatch_text[:40]} if settings.dispatch_text else None,
    }


def promises_of(shop: Shop) -> list[dict]:
    from app.services.storefront import storefront_settings
    defaults = [row for row in _configured_promises(storefront_settings(shop)).values() if row]
    raw = (shop.promises or "").strip()
    if not raw:
        return defaults
    try:
        rows = json.loads(raw)
    except ValueError:
        return defaults
    if not isinstance(rows, list) or not rows:
        return defaults
    return [
        {"title": str(row.get("title", ""))[:16], "sub": str(row.get("sub", ""))[:40]}
        for row in rows
        if isinstance(row, dict) and str(row.get("title", "")).strip()
    ] or defaults


def serialize_sku(sku: Sku, *, purchasable: bool | None = None) -> dict:
    data = {
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
    if purchasable is not None:
        data["purchasable"] = purchasable
    return data


def serialize_product(
    product: Product,
    *,
    audience: str,
    ratings: dict[int, tuple[float, int]] | None = None,
) -> dict:
    """商家端与平台端直接从 SPU/SKU 权威表序列化，拿到的是实时值。

    买家端不调用这里：C 端读的是 c_projection 生成的宽表。
    """
    if audience == "c":
        skus = visible_skus(product)
        sku_rows = [serialize_sku(sku, purchasable=sku.stock > 0) for sku in skus]
    else:
        sku_rows = [serialize_sku(sku) for sku in ordered_skus(product)]
    average, count = (ratings or {}).get(product.id, (None, 0))
    starting_sku = min(sku_rows, key=lambda row: (row["price_yuan"], row["id"]), default=None)
    tags = tags_of(product)
    return {
        "id": product.id,
        "spu_id": product.spu_id,
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
        "market_from": starting_sku["market_price_yuan"] if starting_sku else None,
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
    # 平台账号与店铺其他设置使用同一套商家权限检查。
    shop = merchant_shop(db, user)
    previous_storefront = None
    next_storefront = None
    if body.storefront is not None:
        from app.services.storefront import save_storefront_settings, storefront_settings
        previous_storefront = storefront_settings(shop)
        next_storefront = save_storefront_settings(db, shop, body.storefront)
    if body.assistant_name is not None:
        profile = db.get(ShopAssistantProfile, shop.id)
        if profile is None:
            db.add(ShopAssistantProfile(shop_id=shop.id, name=body.assistant_name, source="custom"))
        else:
            profile.name = body.assistant_name
            profile.source = "custom"
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
    if body.social_accounts is not None:
        shop.social_accounts = json.dumps([row.model_dump() for row in body.social_accounts], ensure_ascii=False)
    if body.promises is not None:
        shop.promises = json.dumps(
            [{"title": row.title.strip(), "sub": row.sub.strip()} for row in body.promises],
            ensure_ascii=False,
        )
    if body.status is not None:
        if body.status == "open" and shop_blocked(shop) and not getattr(user, "_op_operator_id", None):
            raise HTTPException(403, "店铺被平台限制营业，商家不能自行解除")
        shop.status = body.status
    if previous_storefront is not None and shop.promises:
        previous_promises = _configured_promises(previous_storefront)
        next_promises = _configured_promises(next_storefront)
        try:
            rows = json.loads(shop.promises)
        except ValueError:
            rows = []
        if not isinstance(rows, list):
            rows = []
        aligned = []
        for row in rows:
            key = next((key for key, value in previous_promises.items() if row == value), None)
            value = next_promises[key] if key else row
            if value is not None:
                aligned.append(value)
        shop.promises = json.dumps(aligned, ensure_ascii=False)
    db.commit()
    db.refresh(shop)
    # 店铺名/营业状态也会进投影，整店刷一次
    refresh_shop(db, shop.id)
    invalidate_catalog_cache()
    return serialize_shop(shop)


def list_b_products(db: Session, user: User, keyword: str = "", status: str = "") -> list[dict]:
    shop = merchant_shop(db, user)
    products = db.scalars(_product_query().where(Product.shop_id == shop.id)).unique().all()
    if status in {"draft", "on", "off", "banned"}:
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
    """买家端商品列表：展示数据全部来自 C 端宽表，先检查投影版本再读取缓存。"""
    shop = shop_by_code(db, share_code)
    # 店铺营业状态必须在读缓存之前判断，平台冻结店铺才能立刻生效
    if not shop_open(shop):
        return []
    cache_key = f"cache:c-products:{shop.id}:{category or '-'}:{keyword or '-'}:{sort or 'default'}"
    sync_shop(db, shop.id)
    cached = get_redis().get_json(cache_key)
    if cached is None:
        data = [serialize_c(view) for view in view_rows(db, shop.id, keyword=keyword, category=category, sort=sort)]
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
    if not shop_open(shop):
        return []
    sync_shop(db, shop.id)
    used = listed_categories(db, shop.id)
    registered = shop_category_names(db, shop)
    if registered:
        return [name for name in registered if name in used] + [name for name in used if name and name not in registered]
    return used


def get_c_product(db: Session, share_code: str, product_id: int, user: User | None = None) -> dict:
    from fastapi import HTTPException

    shop = shop_by_code(db, share_code)
    if not shop_open(shop):
        raise HTTPException(status_code=404, detail="没有找到这个商品")
    sync_shop(db, shop.id)
    view = view_row(db, shop.id, product_id)
    if view is None:
        raise HTTPException(status_code=404, detail="没有找到这个商品")
    return serialize_c(view)


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
        parameter_profile=SkuParameterProfile(parameters=[item.model_dump() for item in sku.parameters]) if sku.parameters else None,
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
        status=body.status,
        sort_order=max_sort + 1,
        limit_per_user=body.limit_per_user,
    )
    for index, sku in enumerate(body.skus):
        row = _sku_row(sku)
        row.sort_order = index + 1
        product.skus.append(row)
    db.add(product)
    db.commit()
    from app.services.categories import register_category_name

    register_category_name(db, shop.id, product.category)
    sync_product_tags(db, product, body.tag_names)
    db.commit()
    saved = _owned_product(db, user, product.id)
    refresh_product(db, product.id)
    invalidate_catalog_cache()
    return serialize_product(saved, audience="b")


def add_sku(db: Session, user: User, product_id: int, body: SkuIn) -> dict:
    product = _owned_product(db, user, product_id)
    assert_merchant_editable(product)
    spec = body.spec.strip()
    if any(sku.spec == spec for sku in product.skus):
        raise HTTPException(status_code=400, detail="这个规格已经存在")
    row = _sku_row(body)
    row.sort_order = max((sku.sort_order or 0 for sku in product.skus), default=0) + 1
    product.skus.append(row)
    db.commit()
    refresh_product(db, product_id)
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, product_id), audience="b")


def update_product(db: Session, user: User, product_id: int, body: ProductUpdate) -> dict:
    product = _owned_product(db, user, product_id)
    assert_merchant_editable(product)
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
    refresh_product(db, product_id)
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, product_id), audience="b")


def change_product_status(db: Session, user: User, product_id: int, action: str) -> dict:
    product = _owned_product(db, user, product_id)
    assert_merchant_editable(product)
    if action in ("ban", "unban"):
        raise HTTPException(403, "禁售与解禁只能由平台处理")
    if product.status == "draft" and not any(sku.status == "on" for sku in product.skus):
        raise HTTPException(400, "请至少添加一个可售规格，再完成创建或上架")
    product.status = next_status(product.status, action)
    db.commit()
    refresh_product(db, product_id)
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
    assert_merchant_editable(sku.product, sku)
    if body.parameters is not None:
        sku.parameter_profile = SkuParameterProfile(parameters=[item.model_dump() for item in body.parameters]) if sku.parameter_profile is None else sku.parameter_profile
        sku.parameter_profile.parameters = [item.model_dump() for item in body.parameters]
    if body.spec is not None:
        sku.spec = body.spec.strip()
    if body.image_url is not None:
        sku.image_url = body.image_url.strip()
    if body.price_yuan is not None:
        sku.price_cents = to_cents(body.price_yuan)
    if "market_price_yuan" in body.model_fields_set:
        sku.market_price_cents = to_cents(body.market_price_yuan) if body.market_price_yuan is not None else 0
    if body.stock is not None:
        sku.stock = body.stock
    db.commit()
    refresh_product(db, sku.spu_id)
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, sku.spu_id), audience="b")


def change_sku_status(db: Session, user: User, sku_id: int, action: str) -> dict:
    sku = _owned_sku(db, user, sku_id)
    assert_merchant_editable(sku.product, sku)
    if action in ("ban", "unban"):
        raise HTTPException(403, "禁售与解禁只能由平台处理")
    sku.status = next_status(sku.status, action)
    db.commit()
    refresh_product(db, sku.spu_id)
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, sku.spu_id), audience="b")


def reorder_skus(db: Session, user: User, product_id: int, ordered_ids: list[int]) -> dict:
    product = _owned_product(db, user, product_id)
    assert_merchant_editable(product)
    db.execute(select(Product.id).where(Product.id == product.id).with_for_update()).all()
    rows = db.scalars(select(Sku).where(Sku.spu_id == product.id).with_for_update()).all()
    by_id = {row.id: row for row in rows}
    if len(set(ordered_ids)) != len(rows) or len(ordered_ids) != len(rows) or set(ordered_ids) != set(by_id):
        raise HTTPException(409, "规格列表已变化或包含其他商品规格，请刷新后重试")
    if any(row.status == "banned" for row in rows):
        raise HTTPException(403, "存在禁售规格，商家不能调整规格顺序")
    for index, row_id in enumerate(ordered_ids):
        by_id[row_id].sort_order = index + 1
    db.commit()
    db.expire_all()
    refresh_product(db, product_id)
    invalidate_catalog_cache()
    return serialize_product(_owned_product(db, user, product_id), audience="b")


def load_sku_for_shop(db: Session, shop_id: int, sku_id: int) -> Sku | None:
    return db.scalar(
        select(Sku)
        .join(Product)
        .options(joinedload(Sku.product).joinedload(Product.shop))
        .where(Sku.id == sku_id, Product.shop_id == shop_id)
    )


def search_on_sale(db: Session, shop_id: int, keyword: str, limit: int = 5) -> str:
    """助手侧在售商品查询，读的是 C 端宽表，口径与买家看到的一致。"""
    sync_shop(db, shop_id)
    word = keyword.strip()
    views = view_rows(db, shop_id, keyword=word, listed_only=True)[: limit * 4]
    lines = []
    for view in views:
        row = serialize_c(view)
        sku_text = "；".join(
            f"{sku['spec']} ¥{sku['price_yuan']:.2f} 库存{sku['stock']}" for sku in row["skus"]
        )
        lines.append(f"{row['name']}（商品id {row['id']}，{row['category']}）：{sku_text}")
    if not lines:
        return f"没有找到在售商品：{keyword}"
    return "在售商品：\n" + "\n".join(lines)


def describe_inventory(db: Session, shop_id: int, sku_id: int) -> str:
    sku = load_sku_for_shop(db, shop_id, sku_id)
    if sku is None or sku.status != "on" or sku.product.status != "on" or not shop_open(sku.product.shop):
        return "没有找到可售的 SKU。"
    return f"{sku.product.name} / {sku.spec} 库存 {sku.stock}，单价 ¥{yuan(sku.price_cents):.2f}"
