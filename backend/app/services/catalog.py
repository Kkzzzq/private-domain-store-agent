from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.redis_client import get_redis
from app.models.tables import Product, Shop, Sku, User
from app.schemas.dto import ProductIn, ProductUpdate, ShopUpdate, SkuUpdate
from app.services.shelf import listed_on_c, next_status, visible_skus


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
        "share_code": shop.share_code,
        "status": shop.status,
        "share_path": f"/c.html?code={shop.share_code}",
    }


def serialize_sku(sku: Sku, *, purchasable: bool | None = None) -> dict:
    data = {
        "id": sku.id,
        "spec": sku.spec,
        "price_yuan": yuan(sku.price_cents),
        "stock": sku.stock,
        "status": sku.status,
    }
    if purchasable is not None:
        data["purchasable"] = purchasable
    return data


def serialize_product(product: Product, *, audience: str) -> dict:
    if audience == "c":
        skus = visible_skus(product)
        sku_rows = [serialize_sku(sku, purchasable=sku.stock > 0) for sku in skus]
    else:
        sku_rows = [serialize_sku(sku) for sku in product.skus]
    return {
        "id": product.id,
        "shop_id": product.shop_id,
        "name": product.name,
        "category": product.category,
        "description": product.description,
        "image_url": product.image_url,
        "status": product.status,
        "sort_order": product.sort_order,
        "skus": sku_rows,
    }


def _product_query():
    return (
        select(Product)
        .options(joinedload(Product.skus), joinedload(Product.shop))
        .order_by(Product.sort_order.asc(), Product.id.asc())
    )


def update_shop(db: Session, user: User, body: ShopUpdate) -> dict:
    shop = merchant_shop(db, user)
    if body.name is not None:
        shop.name = body.name.strip()
    if body.notice is not None:
        shop.notice = body.notice.strip()
    if body.status is not None:
        shop.status = body.status
    db.commit()
    db.refresh(shop)
    invalidate_catalog_cache()
    return serialize_shop(shop)


def list_b_products(db: Session, user: User) -> list[dict]:
    shop = merchant_shop(db, user)
    products = db.scalars(_product_query().where(Product.shop_id == shop.id)).unique().all()
    return [serialize_product(product, audience="b") for product in products]


def list_c_products(db: Session, share_code: str) -> list[dict]:
    shop = shop_by_code(db, share_code)
    if shop.status != "open":
        return []
    cache_key = f"cache:c-products:{shop.id}"
    cached = get_redis().get_json(cache_key)
    if cached is not None:
        return cached
    products = db.scalars(_product_query().where(Product.shop_id == shop.id)).unique().all()
    data = [serialize_product(product, audience="c") for product in products if listed_on_c(product)]
    get_redis().set_json(cache_key, data, ex=60)
    return data


def _owned_product(db: Session, user: User, product_id: int) -> Product:
    shop = merchant_shop(db, user)
    product = db.scalars(_product_query().where(Product.id == product_id, Product.shop_id == shop.id)).unique().one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="没有找到这个商品")
    return product


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
    )
    for sku in body.skus:
        product.skus.append(
            Sku(spec=sku.spec.strip(), price_cents=to_cents(sku.price_yuan), stock=sku.stock, status="on")
        )
    db.add(product)
    db.commit()
    saved = _owned_product(db, user, product.id)
    invalidate_catalog_cache()
    return serialize_product(saved, audience="b")


def update_product(db: Session, user: User, product_id: int, body: ProductUpdate) -> dict:
    product = _owned_product(db, user, product_id)
    if body.name is not None:
        product.name = body.name.strip()
    if body.description is not None:
        product.description = body.description.strip()
    if body.image_url is not None:
        product.image_url = body.image_url.strip()
    if body.sort_order is not None:
        product.sort_order = body.sort_order
    db.commit()
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
    if body.price_yuan is not None:
        sku.price_cents = to_cents(body.price_yuan)
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
    products = db.scalars(
        _product_query().where(Product.shop_id == shop_id, Product.name.contains(keyword.strip())).limit(limit)
    ).unique().all()
    lines = []
    for product in products:
        if not listed_on_c(product):
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
