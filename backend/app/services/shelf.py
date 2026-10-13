from fastapi import HTTPException

from app.models.tables import Product, Sku

# 当前状态 + 动作 -> 新状态。禁售不能直接上架，必须先解禁回到下架。
_TRANSITIONS = {
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
    if product.shop.status != "open" or product.status != "on":
        return False
    return any(sku.status == "on" for sku in product.skus)


def visible_skus(product: Product) -> list[Sku]:
    if product.shop.status != "open" or product.status != "on":
        return []
    return [sku for sku in product.skus if sku.status == "on"]


def purchase_block(sku: Sku, quantity: int) -> str | None:
    """返回不能买的原因。C 端看不到的规格，不说明是下架还是禁售。"""
    product = sku.product
    if product.shop.status != "open":
        return "店铺未营业"
    if product.status != "on" or sku.status != "on":
        return "没有找到这个商品"
    if sku.stock < quantity:
        return "库存不足"
    return None
