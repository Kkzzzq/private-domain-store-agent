from fastapi import HTTPException
from sqlalchemy.orm import object_session

from app.models.tables import Product, Sku
from app.services.governance import shop_open

# 当前状态 + 动作 -> 新状态。禁售不能直接上架，必须先解禁回到下架。
_TRANSITIONS = {
    ("draft", "on"): "on",
    ("draft", "off"): "off",
    ("off", "on"): "on",
    ("on", "off"): "off",
    ("on", "ban"): "banned",
    ("off", "ban"): "banned",
    ("banned", "unban"): "off",
}


def next_status(current: str, action: str) -> str:
    result = _TRANSITIONS.get((current, action))
    if result is None:
        if current == "banned" and action == "on":
            detail = "禁售商品需要先解禁，不能直接上架"
        elif action == "unban":
            detail = "只有禁售状态可以解禁"
        else:
            detail = "当前状态不能执行这个操作"
        raise HTTPException(status_code=400, detail=detail)
    return result


def listed_on_c(product: Product) -> bool:
    if not shop_open(product.shop) or product.status != "on":
        return False
    return any(sku.status == "on" for sku in product.skus)


def visible_skus(product: Product) -> list[Sku]:
    if not shop_open(product.shop) or product.status != "on":
        return []
    return [sku for sku in ordered_skus(product) if sku.status == "on"]


def ordered_skus(product: Product) -> list[Sku]:
    return sorted(product.skus, key=lambda sku: (sku.sort_order or 0, sku.id or 0))


def assert_merchant_editable(product: Product, sku: Sku | None = None) -> None:
    db = object_session(product)
    if db is not None:
        db.refresh(product, attribute_names=["status"], with_for_update=True)
        if sku is not None:
            db.refresh(sku, attribute_names=["status"], with_for_update=True)
    if product.status == "banned" or (sku is not None and sku.status == "banned"):
        raise HTTPException(403, "商品或规格已被平台禁售，商家不能编辑、排序、上下架或解禁，请联系平台处理")


def purchase_block(sku: Sku, quantity: int) -> str | None:
    """返回不能买的原因。C 端看不到的规格，不说明是下架还是禁售。"""
    product = sku.product
    if not shop_open(product.shop):
        return "店铺未营业"
    if product.status != "on" or sku.status != "on":
        return "没有找到这个商品"
    if sku.stock < quantity:
        return "库存不足"
    return None
