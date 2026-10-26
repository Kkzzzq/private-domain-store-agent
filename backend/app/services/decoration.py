import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.models.tables import Banner, Product, ProductTag, Section, Shop, ShopCategory, Testimonial
from app.schemas.decoration import DecorationDraft
from app.services.catalog import _configured_promises, invalidate_catalog_cache, merchant_shop, serialize_product, serialize_shop
from app.services.c_projection import refresh_shop, serialize_c
from app.services.home import _replace_items, _visible_views, list_banners, list_sections, list_testimonials
from app.services.storefront import save_storefront_settings, storefront_settings


def decoration_snapshot(db, user):
    shop = merchant_shop(db, user)
    payload = serialize_shop(shop)
    data = {
        "appearance": {key: payload[key] for key in ("hero_height", "strip_tint", "promises", "storefront")},
        "banners": list_banners(db, user),
        "sections": list_sections(db, user),
        "testimonials": list_testimonials(db, user),
    }
    data["revision"] = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return data


def _validate_scope(db, shop, draft):
    for model, submitted in ((Banner, draft.banners), (Section, draft.sections), (Testimonial, draft.testimonials)):
        own = set(db.scalars(select(model.id).where(model.shop_id == shop.id)).all())
        if any(row.id > 0 and row.id not in own for row in submitted):
            raise HTTPException(409, "装修内容已变更或不属于本店，请重新加载")
    products = set(db.scalars(select(Product.id).where(Product.shop_id == shop.id)).all())
    section_ids = {row.id for row in draft.sections}
    if any(product_id not in products for section in draft.sections for product_id in section.product_ids):
        raise HTTPException(422, "栏目只能选择本店商品")
    for banner in draft.banners:
        if banner.link_type == "none":
            continue
        try:
            target = int(banner.link_value)
        except ValueError as error:
            raise HTTPException(422, "轮播跳转目标无效") from error
        allowed = products if banner.link_type == "product" else section_ids
        if target not in allowed:
            raise HTTPException(422, "轮播只能跳转本店商品或草稿中的栏目")


def _appearance(shop, draft):
    data = draft.appearance.model_dump()
    previous = _configured_promises(storefront_settings(shop))
    current = _configured_promises(draft.appearance.storefront)
    rows = data["promises"]
    aligned = []
    for row in rows:
        key = next((key for key, value in previous.items() if value == row), None)
        value = current[key] if key else row
        if value:
            aligned.append(value)
    data["promises"] = aligned or [row for row in current.values() if row]
    return data


def preview_decoration(db, user, draft: DecorationDraft):
    shop = merchant_shop(db, user)
    _validate_scope(db, shop, draft)
    shop_payload = serialize_shop(shop)
    shop_payload.update(_appearance(shop, draft))
    visible = _visible_views(db, shop)
    products = [serialize_c(view) for view in visible]
    by_id = {product["id"]: product for product in products}
    sections = []
    for row in draft.sections:
        if not row.enabled:
            continue
        selected = sorted(products, key=lambda product: product["sales_count"], reverse=True)[:6] if row.source == "sales" else [
            by_id[product_id] for product_id in dict.fromkeys(row.product_ids) if product_id in by_id
        ][:6]
        if selected:
            sections.append({"id": row.id, "title": row.title, "subtitle": row.subtitle, "products": selected})
    return {"home": {
        "shop": shop_payload,
        "banners": [row.model_dump() for row in draft.banners if row.enabled],
        "sections": sections,
        "testimonials": [row.model_dump() for row in draft.testimonials if row.enabled],
    }, "products": products}


def _locked_shop(db, user):
    user_id = user.id
    db.rollback()
    shop = db.scalar(select(Shop).where(Shop.merchant_id == user_id).with_for_update())
    if shop is None:
        raise HTTPException(404, "还没有店铺")
    return shop


def save_decoration(db, user, draft: DecorationDraft):
    shop = _locked_shop(db, user)
    if decoration_snapshot(db, user)["revision"] != draft.revision:
        raise HTTPException(409, "店铺装修已被其他页面修改，请先重新加载，避免覆盖")
    _validate_scope(db, shop, draft)
    appearance = _appearance(shop, draft)
    shop.hero_height = appearance["hero_height"]
    shop.strip_tint = appearance["strip_tint"]
    shop.promises = json.dumps(appearance["promises"], ensure_ascii=False)
    save_storefront_settings(db, shop, draft.appearance.storefront)
    section_map = {}
    for model, submitted in ((Section, draft.sections), (Banner, draft.banners), (Testimonial, draft.testimonials)):
        existing = {row.id: row for row in db.scalars(select(model).where(model.shop_id == shop.id)).all()}
        retained = {row.id for row in submitted if row.id > 0}
        for row_id, row in existing.items():
            if row_id not in retained:
                db.delete(row)
        for index, item in enumerate(submitted):
            row = existing.get(item.id) if item.id > 0 else model(shop_id=shop.id)
            fields = item.model_dump(exclude={"id", "product_ids"})
            if model is Banner and item.link_type == "section":
                fields["link_value"] = str(section_map[int(item.link_value)])
            for key, value in fields.items():
                setattr(row, key, value.strip() if isinstance(value, str) else value)
            row.sort_order = index + 1
            db.add(row)
            db.flush()
            if model is Section:
                section_map[item.id] = row.id
                _replace_items(db, row, item.product_ids)
    db.commit()
    db.expire_all()
    invalidate_catalog_cache()
    return decoration_snapshot(db, user)


def reorder(db, user, kind, ordered_ids):
    models = {"categories": ShopCategory, "tags": ProductTag, "banners": Banner, "sections": Section, "testimonials": Testimonial}
    model = models.get(kind)
    if model is None:
        raise HTTPException(404, "不支持的排序类型")
    shop = _locked_shop(db, user)
    rows = db.scalars(select(model).where(model.shop_id == shop.id).with_for_update()).all()
    by_id = {row.id: row for row in rows}
    if len(ordered_ids) != len(by_id) or set(ordered_ids) != set(by_id):
        raise HTTPException(409, "列表内容已变化或包含其他店铺数据，请刷新后重试")
    for index, row_id in enumerate(ordered_ids):
        by_id[row_id].sort_order = index + 1
    db.commit()
    if kind == "tags":
        refresh_shop(db, shop.id)
    invalidate_catalog_cache()
    return {"ok": True, "ordered_ids": ordered_ids}
