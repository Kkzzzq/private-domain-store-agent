"""首页内容：轮播图、栏目位和用户评价。商家在后台配，买家端只读。"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.tables import Banner, Product, Section, SectionItem, Shop, Testimonial, User
from app.schemas.dto import (
    BannerIn,
    BannerUpdate,
    SectionIn,
    SectionUpdate,
    TestimonialIn,
    TestimonialUpdate,
)
from app.services.catalog import (
    _product_query,
    merchant_shop,
    serialize_product,
    serialize_shop,
    shop_by_code,
)
from app.services.engagement import favorite_ids
from app.services.reviews import rating_map
from app.services.shelf import listed_on_c

SECTION_LIMIT = 6


# ---------- 序列化 ----------
def serialize_banner(banner: Banner) -> dict:
    return {
        "id": banner.id,
        "image_url": banner.image_url,
        "title": banner.title,
        "subtitle": banner.subtitle,
        "link_type": banner.link_type,
        "link_value": banner.link_value,
        "sort_order": banner.sort_order,
        "enabled": banner.enabled,
    }


def serialize_testimonial(row: Testimonial) -> dict:
    return {
        "id": row.id,
        "nickname": row.nickname,
        "content": row.content,
        "rating": row.rating,
        "sort_order": row.sort_order,
        "enabled": row.enabled,
    }


def serialize_section(section: Section) -> dict:
    return {
        "id": section.id,
        "title": section.title,
        "subtitle": section.subtitle,
        "source": section.source,
        "sort_order": section.sort_order,
        "enabled": section.enabled,
        "product_ids": [item.product_id for item in sorted(section.items, key=lambda i: i.sort_order)],
        "product_names": [
            item.product.name for item in sorted(section.items, key=lambda i: i.sort_order) if item.product
        ],
    }


# ---------- 买家端 ----------
def _visible_products(db: Session, shop: Shop) -> list[Product]:
    rows = db.scalars(_product_query().where(Product.shop_id == shop.id)).unique().all()
    return [product for product in rows if listed_on_c(product)]


def _section_products(db: Session, section: Section, visible: list[Product]) -> list[Product]:
    if section.source == "sales":
        return sorted(visible, key=lambda product: product.sales_count, reverse=True)[:SECTION_LIMIT]
    order = {item.product_id: item.sort_order for item in section.items}
    picked = [product for product in visible if product.id in order]
    picked.sort(key=lambda product: order[product.id])
    return picked[:SECTION_LIMIT]


def home_content(db: Session, share_code: str, user: User | None = None) -> dict:
    shop = shop_by_code(db, share_code)
    shop_payload = serialize_shop(shop)
    if shop.status != "open":
        return {"banners": [], "sections": [], "testimonials": [], "shop": shop_payload}

    banners = db.scalars(
        select(Banner)
        .where(Banner.shop_id == shop.id, Banner.enabled.is_(True))
        .order_by(Banner.sort_order.asc(), Banner.id.asc())
    ).all()
    testimonials = db.scalars(
        select(Testimonial)
        .where(Testimonial.shop_id == shop.id, Testimonial.enabled.is_(True))
        .order_by(Testimonial.sort_order.asc(), Testimonial.id.asc())
    ).all()
    sections = db.scalars(
        select(Section)
        .options(joinedload(Section.items).joinedload(SectionItem.product))
        .where(Section.shop_id == shop.id, Section.enabled.is_(True))
        .order_by(Section.sort_order.asc(), Section.id.asc())
    ).unique().all()

    visible = _visible_products(db, shop)
    ratings = rating_map(db, [product.id for product in visible])
    favorites = favorite_ids(db, user)

    def as_dict(product: Product) -> dict:
        return serialize_product(product, audience="c", ratings=ratings, favorites=favorites)

    rows = []
    for section in sections:
        products = _section_products(db, section, visible)
        if not products:
            continue
        rows.append(
            {
                "id": section.id,
                "title": section.title,
                "subtitle": section.subtitle,
                "products": [as_dict(product) for product in products],
            }
        )
    return {
        "banners": [serialize_banner(banner) for banner in banners],
        "sections": rows,
        "testimonials": [serialize_testimonial(row) for row in testimonials],
        "shop": shop_payload,
    }


# ---------- 商家端 ----------
def list_banners(db: Session, user: User) -> list[dict]:
    shop = merchant_shop(db, user)
    rows = db.scalars(
        select(Banner).where(Banner.shop_id == shop.id).order_by(Banner.sort_order.asc(), Banner.id.asc())
    ).all()
    return [serialize_banner(row) for row in rows]


def create_banner(db: Session, user: User, body: BannerIn) -> dict:
    shop = merchant_shop(db, user)
    max_sort = db.scalar(select(func.max(Banner.sort_order)).where(Banner.shop_id == shop.id)) or 0
    banner = Banner(
        shop_id=shop.id,
        sort_order=max_sort + 1,
        image_url=body.image_url.strip(),
        title=body.title.strip(),
        subtitle=body.subtitle.strip(),
        link_type=body.link_type,
        link_value=body.link_value.strip(),
        enabled=body.enabled,
    )
    db.add(banner)
    db.commit()
    db.refresh(banner)
    return serialize_banner(banner)


def update_banner(db: Session, user: User, banner_id: int, body: BannerUpdate) -> dict:
    from fastapi import HTTPException

    shop = merchant_shop(db, user)
    banner = db.scalar(select(Banner).where(Banner.id == banner_id, Banner.shop_id == shop.id))
    if banner is None:
        raise HTTPException(status_code=404, detail="没有找到这张图")
    for field in ("image_url", "title", "subtitle", "link_type", "link_value", "sort_order", "enabled"):
        value = getattr(body, field)
        if value is not None:
            setattr(banner, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(banner)
    return serialize_banner(banner)


def delete_banner(db: Session, user: User, banner_id: int) -> None:
    from fastapi import HTTPException

    shop = merchant_shop(db, user)
    banner = db.scalar(select(Banner).where(Banner.id == banner_id, Banner.shop_id == shop.id))
    if banner is None:
        raise HTTPException(status_code=404, detail="没有找到这张图")
    db.delete(banner)
    db.commit()


def list_sections(db: Session, user: User) -> list[dict]:
    shop = merchant_shop(db, user)
    rows = db.scalars(
        select(Section)
        .options(joinedload(Section.items).joinedload(SectionItem.product))
        .where(Section.shop_id == shop.id)
        .order_by(Section.sort_order.asc(), Section.id.asc())
    ).unique().all()
    return [serialize_section(row) for row in rows]


def _replace_items(db: Session, section: Section, product_ids: list[int]) -> None:
    db.execute(delete(SectionItem).where(SectionItem.section_id == section.id))
    for index, product_id in enumerate(dict.fromkeys(product_ids)):
        db.add(SectionItem(section_id=section.id, product_id=product_id, sort_order=index))


def create_section(db: Session, user: User, body: SectionIn) -> dict:
    shop = merchant_shop(db, user)
    max_sort = db.scalar(select(func.max(Section.sort_order)).where(Section.shop_id == shop.id)) or 0
    section = Section(
        shop_id=shop.id,
        title=body.title.strip(),
        subtitle=body.subtitle.strip(),
        source=body.source,
        enabled=body.enabled,
        sort_order=max_sort + 1,
    )
    db.add(section)
    db.flush()
    _replace_items(db, section, body.product_ids)
    db.commit()
    return _reload_section(db, shop.id, section.id)


def _reload_section(db: Session, shop_id: int, section_id: int) -> dict:
    row = db.scalars(
        select(Section)
        .options(joinedload(Section.items).joinedload(SectionItem.product))
        .where(Section.id == section_id, Section.shop_id == shop_id)
    ).unique().one()
    return serialize_section(row)


def update_section(db: Session, user: User, section_id: int, body: SectionUpdate) -> dict:
    from fastapi import HTTPException

    shop = merchant_shop(db, user)
    section = db.scalar(select(Section).where(Section.id == section_id, Section.shop_id == shop.id))
    if section is None:
        raise HTTPException(status_code=404, detail="没有找到这个栏目")
    for field in ("title", "subtitle", "source", "sort_order", "enabled"):
        value = getattr(body, field)
        if value is not None:
            setattr(section, field, value.strip() if isinstance(value, str) else value)
    if body.product_ids is not None:
        _replace_items(db, section, body.product_ids)
    db.commit()
    return _reload_section(db, shop.id, section.id)


def delete_section(db: Session, user: User, section_id: int) -> None:
    from fastapi import HTTPException

    shop = merchant_shop(db, user)
    section = db.scalar(select(Section).where(Section.id == section_id, Section.shop_id == shop.id))
    if section is None:
        raise HTTPException(status_code=404, detail="没有找到这个栏目")
    db.delete(section)
    db.commit()


def list_testimonials(db: Session, user: User) -> list[dict]:
    shop = merchant_shop(db, user)
    rows = db.scalars(
        select(Testimonial)
        .where(Testimonial.shop_id == shop.id)
        .order_by(Testimonial.sort_order.asc(), Testimonial.id.asc())
    ).all()
    return [serialize_testimonial(row) for row in rows]


def create_testimonial(db: Session, user: User, body: TestimonialIn) -> dict:
    shop = merchant_shop(db, user)
    max_sort = (
        db.scalar(select(func.max(Testimonial.sort_order)).where(Testimonial.shop_id == shop.id)) or 0
    )
    row = Testimonial(
        shop_id=shop.id,
        nickname=body.nickname.strip(),
        content=body.content.strip(),
        rating=body.rating,
        enabled=body.enabled,
        sort_order=max_sort + 1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_testimonial(row)


def update_testimonial(db: Session, user: User, row_id: int, body: TestimonialUpdate) -> dict:
    from fastapi import HTTPException

    shop = merchant_shop(db, user)
    row = db.scalar(select(Testimonial).where(Testimonial.id == row_id, Testimonial.shop_id == shop.id))
    if row is None:
        raise HTTPException(status_code=404, detail="没有找到这条评价")
    for field in ("nickname", "content", "rating", "sort_order", "enabled"):
        value = getattr(body, field)
        if value is not None:
            setattr(row, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(row)
    return serialize_testimonial(row)


def delete_testimonial(db: Session, user: User, row_id: int) -> None:
    from fastapi import HTTPException

    shop = merchant_shop(db, user)
    row = db.scalar(select(Testimonial).where(Testimonial.id == row_id, Testimonial.shop_id == shop.id))
    if row is None:
        raise HTTPException(status_code=404, detail="没有找到这条评价")
    db.delete(row)
    db.commit()
