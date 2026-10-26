from app.services.governance import shop_open
"""首页内容：轮播图、栏目位和用户评价。商家在后台配，买家端只读。"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.tables import Banner, CProductView, Section, SectionItem, Shop, Testimonial, User
from app.schemas.dto import (
    BannerIn,
    BannerUpdate,
    SectionIn,
    SectionUpdate,
    TestimonialIn,
    TestimonialUpdate,
)
from app.services.c_projection import serialize_c, sync_shop, view_rows
from app.services.catalog import (
    merchant_shop,
    serialize_shop,
    shop_by_code,
)
from app.services.categories import shop_category_names
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
def _visible_views(db: Session, shop: Shop) -> list[CProductView]:
    """买家端可见商品全部取自 C 端宽表。"""
    sync_shop(db, shop.id)
    return view_rows(db, shop.id, listed_only=True)


def _section_views(section: Section, visible: list[CProductView]) -> list[CProductView]:
    if section.source == "sales":
        return sorted(visible, key=lambda row: row.sales_count or 0, reverse=True)[:SECTION_LIMIT]
    order = {item.product_id: item.sort_order for item in section.items}
    picked = [row for row in visible if row.spu_id in order]
    picked.sort(key=lambda row: order[row.spu_id])
    return picked[:SECTION_LIMIT]


def home_content(db: Session, share_code: str, user: User | None = None) -> dict:
    shop = shop_by_code(db, share_code)
    shop_payload = serialize_shop(shop)
    if not shop_open(shop):
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

    visible = _visible_views(db, shop)
    rows = []
    for section in sections:
        products = _section_views(section, visible)
        if not products:
            continue
        rows.append(
            {
                "id": section.id,
                "title": section.title,
                "subtitle": section.subtitle,
                "products": [serialize_c(view) for view in products],
            }
        )
    return {
        "banners": [serialize_banner(banner) for banner in banners],
        "sections": rows,
        "testimonials": [serialize_testimonial(row) for row in testimonials],
        "shop": shop_payload,
    }


def collection_page(
    db: Session,
    share_code: str,
    key: str,
    user: User | None = None,
    keyword: str = "",
    category: str = "",
    sort: str = "default",
) -> dict:
    """合集页：某一行的完整商品列表，带左侧筛选。

    key 为 "all" 时是全部在售商品；否则是某个栏目的商品。
    栏目在首页只展示前 6 件，合集页给全量。
    """
    from fastapi import HTTPException

    shop = shop_by_code(db, share_code)
    visible = _visible_views(db, shop) if shop_open(shop) else []
    source = "all"

    if key == "all":
        title, subtitle, pool = "全部商品", "店里所有在售的东西", list(visible)
    else:
        try:
            section_id = int(key)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="没有找到这个合集") from exc
        section = db.scalars(
            select(Section)
            .options(joinedload(Section.items).joinedload(SectionItem.product))
            .where(Section.id == section_id, Section.shop_id == shop.id, Section.enabled.is_(True))
        ).unique().one_or_none()
        if section is None:
            raise HTTPException(status_code=404, detail="没有找到这个合集")
        title, subtitle = section.title, section.subtitle
        source = section.source
        if section.source == "sales":
            pool = sorted(visible, key=lambda row: row.sales_count or 0, reverse=True)
        else:
            order = {item.product_id: item.sort_order for item in section.items}
            pool = [row for row in visible if row.spu_id in order]
            pool.sort(key=lambda row: order[row.spu_id])

    # 左侧筛选用的分类标签：商家自己定义的那套顺序优先
    counts: dict[str, int] = {}
    for view in pool:
        if not view.category:
            continue
        counts[view.category] = counts.get(view.category, 0) + 1
    registered = shop_category_names(db, shop)
    categories = [name for name in registered if counts.get(name)]
    if key == "all":
        # 全部商品页把商家定义过的标签都列出来，方便买家知道店里有哪些类目
        categories += [name for name in registered if not counts.get(name)]
    categories += [name for name in counts if name not in registered]

    rows = list(pool)
    if category:
        rows = [view for view in rows if view.category == category]
    if keyword:
        word = keyword.strip()
        rows = [view for view in rows if word in view.name or word in view.category]
    if sort == "price_asc":
        rows.sort(key=lambda view: view.price_from_cents or 0)
    elif sort == "price_desc":
        rows.sort(key=lambda view: view.price_from_cents or 0, reverse=True)
    elif sort == "sales":
        rows.sort(key=lambda view: view.sales_count or 0, reverse=True)

    return {
        "key": key,
        "title": title,
        "subtitle": subtitle,
        "source": source,
        "categories": categories,
        "category_counts": counts,
        "total": len(pool),
        "products": [serialize_c(view) for view in rows],
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
