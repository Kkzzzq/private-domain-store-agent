import json
from decimal import Decimal

from sqlalchemy.orm import object_session

from app.models.tables import ShopStorefrontProfile
from app.schemas.storefront import StorefrontSettings


def storefront_settings(shop):
    db = object_session(shop)
    row = db.get(ShopStorefrontProfile, shop.id) if db and shop.id else None
    return StorefrontSettings.model_validate_json(row.settings) if row else StorefrontSettings()


def save_storefront_settings(db, shop, settings):
    merged = storefront_settings(shop).model_dump()
    merged.update(settings.model_dump(exclude_unset=True))
    row = db.get(ShopStorefrontProfile, shop.id)
    if row is None:
        row = ShopStorefrontProfile(shop_id=shop.id)
        db.add(row)
    validated = StorefrontSettings.model_validate(merged)
    row.settings = json.dumps(validated.model_dump(), ensure_ascii=False)
    return validated


def shipping_promise(settings):
    free = not settings.free_shipping_yuan or not settings.base_freight_yuan
    return {"title": "全店包邮" if free else f"满 {money_label(settings.free_shipping_yuan)} 包邮",
            "sub": "无额外运费" if free else f"未满收 {money_label(settings.base_freight_yuan)} 元运费"}


def money_label(value):
    return format(Decimal(str(value)).normalize(), "f")
