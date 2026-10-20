"""商家的自定义分类标签。

合集页左侧的筛选项、商品编辑里的类目下拉，都用这里维护的标签。
商品表里仍然存类目名（字符串），所以改名时要顺手把已有商品一起改，
否则会出现「标签改了但商品还挂在旧类目上」的错位。
"""

from sqlalchemy import func, select

from app.models.tables import Product, Shop, ShopCategory, User
from app.schemas.dto import CategoryIn, CategoryUpdate
from app.services.catalog import invalidate_catalog_cache, merchant_shop


def serialize_category(row: ShopCategory, count: int = 0) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "sort_order": row.sort_order,
        "product_count": count,
    }


def counts_for_shop(db, shop_id: int) -> dict[str, int]:
    rows = db.execute(
        select(Product.category, func.count(Product.id)).where(Product.shop_id == shop_id).group_by(Product.category)
    ).all()
    return {name: int(total) for name, total in rows if name}


def list_categories(db, user: User) -> list[dict]:
    shop = merchant_shop(db, user)
    rows = db.scalars(
        select(ShopCategory).where(ShopCategory.shop_id == shop.id).order_by(ShopCategory.sort_order, ShopCategory.id)
    ).all()
    counts = counts_for_shop(db, shop.id)
    return [serialize_category(row, counts.get(row.name, 0)) for row in rows]


def shop_category_names(db, shop: Shop) -> list[str]:
    rows = db.scalars(
        select(ShopCategory).where(ShopCategory.shop_id == shop.id).order_by(ShopCategory.sort_order, ShopCategory.id)
    ).all()
    return [row.name for row in rows]


def _duplicate(db, shop_id: int, name: str, exclude_id: int | None = None) -> bool:
    query = select(ShopCategory.id).where(ShopCategory.shop_id == shop_id, ShopCategory.name == name)
    if exclude_id is not None:
        query = query.where(ShopCategory.id != exclude_id)
    return db.scalar(query) is not None


def create_category(db, user: User, body: CategoryIn) -> dict:
    from fastapi import HTTPException

    shop = merchant_shop(db, user)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="分类名称不能为空")
    if _duplicate(db, shop.id, name):
        raise HTTPException(status_code=409, detail="已经有同名分类了")
    max_sort = db.scalar(select(func.max(ShopCategory.sort_order)).where(ShopCategory.shop_id == shop.id)) or 0
    row = ShopCategory(shop_id=shop.id, name=name, sort_order=max_sort + 1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_category(row)


def update_category(db, user: User, category_id: int, body: CategoryUpdate) -> dict:
    from fastapi import HTTPException

    shop = merchant_shop(db, user)
    row = db.scalar(select(ShopCategory).where(ShopCategory.id == category_id, ShopCategory.shop_id == shop.id))
    if row is None:
        raise HTTPException(status_code=404, detail="没有找到这个分类")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="分类名称不能为空")
        if _duplicate(db, shop.id, name, exclude_id=row.id):
            raise HTTPException(status_code=409, detail="已经有同名分类了")
        # 标签改名时，把挂在这个类目下的商品一起搬过去
        if name != row.name:
            products = db.scalars(
                select(Product).where(Product.shop_id == shop.id, Product.category == row.name)
            ).all()
            for product in products:
                product.category = name
        row.name = name
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    db.commit()
    db.refresh(row)
    invalidate_catalog_cache()
    counts = counts_for_shop(db, shop.id)
    return serialize_category(row, counts.get(row.name, 0))


def delete_category(db, user: User, category_id: int) -> None:
    from fastapi import HTTPException

    shop = merchant_shop(db, user)
    row = db.scalar(select(ShopCategory).where(ShopCategory.id == category_id, ShopCategory.shop_id == shop.id))
    if row is None:
        raise HTTPException(status_code=404, detail="没有找到这个分类")
    # 还有商品挂着时不让删，避免商品变成没有分类的孤儿
    used = db.scalar(
        select(func.count(Product.id)).where(Product.shop_id == shop.id, Product.category == row.name)
    )
    if used:
        raise HTTPException(status_code=400, detail=f"还有 {used} 件商品挂在这个分类下，先改掉再删")
    db.delete(row)
    db.commit()


def register_category_name(db, shop_id: int, name: str, *, commit: bool = True) -> None:
    """商品保存时如果写了个新类目名，顺手登记成标签，避免出现游离类目。"""
    name = (name or "").strip()
    if not name:
        return
    exists = db.scalar(select(ShopCategory.id).where(ShopCategory.shop_id == shop_id, ShopCategory.name == name))
    if exists is not None:
        return
    max_sort = db.scalar(select(func.max(ShopCategory.sort_order)).where(ShopCategory.shop_id == shop_id)) or 0
    db.add(ShopCategory(shop_id=shop_id, name=name, sort_order=max_sort + 1))
    if commit:
        db.commit()


def ensure_from_products(db, shop: Shop) -> None:
    """把商品里已经用到的类目补进标签表，保证旧数据不丢。"""
    existing = {row.name for row in db.scalars(select(ShopCategory).where(ShopCategory.shop_id == shop.id)).all()}
    names: list[str] = []
    for product in db.scalars(select(Product).where(Product.shop_id == shop.id)).all():
        if product.category and product.category not in existing and product.category not in names:
            names.append(product.category)
    if not names:
        return
    start = db.scalar(select(func.max(ShopCategory.sort_order)).where(ShopCategory.shop_id == shop.id)) or 0
    for offset, name in enumerate(names):
        db.add(ShopCategory(shop_id=shop.id, name=name, sort_order=start + offset + 1))
    db.commit()
