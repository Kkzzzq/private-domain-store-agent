"""商家的商品标签。

买家端商品卡左上角那个小角标（促销 / 爆款 / 新上线 …）就是这里的标签。
标签只属于一家店，商品和标签是多对多：改标签名不用动关联表，因为存的是 id。
"""

from sqlalchemy import func, select

from app.models.tables import Product, ProductTag, ProductTagLink, ProductTagStyle, Shop, User
from app.schemas.dto import TagIn, TagUpdate

# 建店时先给一套常用的，商家不喜欢可以改名或删掉
DEFAULT_TAGS = [
    ("促销", "#ff5000"),
    ("爆款", "#e5484d"),
    ("新上线", "#1f8a52"),
    ("折扣", "#c9502f"),
]


def _invalidate() -> None:
    # 放在函数里取，避免和 catalog 互相 import
    from app.services.catalog import invalidate_catalog_cache

    invalidate_catalog_cache()


def _merchant_shop(db, user):
    from app.services.catalog import merchant_shop

    return merchant_shop(db, user)


def serialize_tag(row: ProductTag, count: int = 0) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "color": row.color or "",
        **style_of(row),
        "sort_order": row.sort_order,
        "product_count": count,
    }


def style_of(row: ProductTag) -> dict:
    profile = row.style_profile
    return {key: getattr(profile, key, "") if profile else ""
            for key in ("background_color", "border_color", "text_color")}


def save_style(row: ProductTag, body) -> None:
    values = body.model_dump(exclude_unset=True)
    colors = {key: values[key] for key in ("background_color", "border_color", "text_color")
              if key in values and values[key] is not None}
    if colors:
        if row.style_profile is None:
            row.style_profile = ProductTagStyle()
        for key, value in colors.items():
            setattr(row.style_profile, key, value)


def counts_for_shop(db, shop_id: int) -> dict[int, int]:
    rows = db.execute(
        select(ProductTagLink.tag_id, func.count(ProductTagLink.id))
        .join(Product, Product.id == ProductTagLink.product_id)
        .where(Product.shop_id == shop_id)
        .group_by(ProductTagLink.tag_id)
    ).all()
    return {tag_id: int(total) for tag_id, total in rows}


def list_tags(db, user: User) -> list[dict]:
    shop = _merchant_shop(db, user)
    rows = db.scalars(
        select(ProductTag).where(ProductTag.shop_id == shop.id).order_by(ProductTag.sort_order, ProductTag.id)
    ).all()
    counts = counts_for_shop(db, shop.id)
    return [serialize_tag(row, counts.get(row.id, 0)) for row in rows]


def shop_tags(db, shop: Shop) -> list[ProductTag]:
    return list(
        db.scalars(
            select(ProductTag).where(ProductTag.shop_id == shop.id).order_by(ProductTag.sort_order, ProductTag.id)
        ).all()
    )


def _duplicate(db, shop_id: int, name: str, exclude_id: int | None = None) -> bool:
    query = select(ProductTag.id).where(ProductTag.shop_id == shop_id, ProductTag.name == name)
    if exclude_id is not None:
        query = query.where(ProductTag.id != exclude_id)
    return db.scalar(query) is not None


def create_tag(db, user: User, body: TagIn) -> dict:
    from fastapi import HTTPException

    shop = _merchant_shop(db, user)
    name = body.name.strip()
    if _duplicate(db, shop.id, name):
        raise HTTPException(status_code=409, detail="已经有同名标签了")
    max_sort = db.scalar(select(func.max(ProductTag.sort_order)).where(ProductTag.shop_id == shop.id)) or 0
    row = ProductTag(shop_id=shop.id, name=name, color=(body.color or "").strip(), sort_order=max_sort + 1)
    save_style(row, body)
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_tag(row)


def update_tag(db, user: User, tag_id: int, body: TagUpdate) -> dict:
    from fastapi import HTTPException

    shop = _merchant_shop(db, user)
    row = db.scalar(select(ProductTag).where(ProductTag.id == tag_id, ProductTag.shop_id == shop.id))
    if row is None:
        raise HTTPException(status_code=404, detail="没有找到这个标签")
    if body.name is not None:
        name = body.name.strip()
        if _duplicate(db, shop.id, name, exclude_id=row.id):
            raise HTTPException(status_code=409, detail="已经有同名标签了")
        row.name = name
    if body.color is not None:
        row.color = body.color.strip()
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    save_style(row, body)
    db.commit()
    db.refresh(row)
    _invalidate()
    counts = counts_for_shop(db, shop.id)
    return serialize_tag(row, counts.get(row.id, 0))


def delete_tag(db, user: User, tag_id: int) -> None:
    from fastapi import HTTPException

    shop = _merchant_shop(db, user)
    row = db.scalar(select(ProductTag).where(ProductTag.id == tag_id, ProductTag.shop_id == shop.id))
    if row is None:
        raise HTTPException(status_code=404, detail="没有找到这个标签")
    # 先摘干净挂着的商品，再删标签本身
    for link in db.scalars(select(ProductTagLink).where(ProductTagLink.tag_id == row.id)).all():
        db.delete(link)
    db.delete(row)
    db.commit()
    _invalidate()


def tags_of(product: Product) -> list[dict]:
    """按商家定义的顺序给出这件商品的标签，卡片左上角取第一个。"""
    links = sorted(product.tag_links, key=lambda link: (link.tag.sort_order, link.tag.id))
    return [{"name": link.tag.name, "color": link.tag.color or "", **style_of(link.tag)} for link in links]


def sync_product_tags(db, product: Product, names: list[str]) -> None:
    """把商品的标签整批换成 names，没有的标签顺手建出来。"""
    shop_id = product.shop_id
    wanted: list[str] = []
    for raw in names:
        name = (raw or "").strip()
        if name and name not in wanted:
            wanted.append(name)

    known = {row.name: row for row in shop_tags_for(db, shop_id)}
    max_sort = db.scalar(select(func.max(ProductTag.sort_order)).where(ProductTag.shop_id == shop_id)) or 0
    for name in wanted:
        if name not in known:
            max_sort += 1
            row = ProductTag(shop_id=shop_id, name=name, color="", sort_order=max_sort)
            db.add(row)
            db.flush()
            known[name] = row

    for link in list(product.tag_links):
        if link.tag.name not in wanted:
            db.delete(link)
    current = {link.tag.name for link in product.tag_links if link.tag.name in wanted}
    for name in wanted:
        if name in current:
            continue
        product.tag_links.append(ProductTagLink(tag=known[name]))


def shop_tags_for(db, shop_id: int) -> list[ProductTag]:
    return list(db.scalars(select(ProductTag).where(ProductTag.shop_id == shop_id)).all())


def ensure_defaults(db, shop: Shop) -> None:
    """建店 / 老库升级时补一套默认标签，已经有标签的店不动。"""
    if db.scalar(select(ProductTag.id).where(ProductTag.shop_id == shop.id)) is not None:
        return
    for index, (name, color) in enumerate(DEFAULT_TAGS, start=1):
        db.add(ProductTag(shop_id=shop.id, name=name, color=color, sort_order=index))
    db.commit()
