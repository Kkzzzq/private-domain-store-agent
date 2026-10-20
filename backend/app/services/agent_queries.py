import json
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.agent.context import current
from app.models.tables import Order, Product
from app.services.catalog import _product_query, serialize_product, yuan
from app.services.engagement import _recent_ids
from app.services.orders import STATUS_LABELS, _orders
from app.services.shelf import listed_on_c


def store_catalog(offset=0, limit=16):
    db, actor = current()
    products = db.scalars(_product_query().where(Product.shop_id == actor.shop_id)).unique().all()
    rows = [serialize_product(product, audience="c") for product in products if listed_on_c(product)]
    for row in rows:
        row["skus"] = [sku for sku in row["skus"] if sku["stock"] > 0]
    rows = [row for row in rows if row["skus"]]
    categories = Counter(row["category"] for row in rows)
    prices = [sku["price_yuan"] for row in rows for sku in row["skus"]]
    page = []
    for row in rows[offset:offset + limit]:
        item = {"id": row["id"], "name": row["name"], "category": row["category"],
                "description": row["description"][:120], "limit_per_user": row["limit_per_user"],
                "sku_count": len(row["skus"]), "sku_details_truncated": len(row["skus"]) > 4,
                "skus": [{"id": sku["id"], "spec": sku["spec"], "price_yuan": sku["price_yuan"], "stock": sku["stock"]} for sku in row["skus"][:4]]}
        if page and len(json.dumps(page + [item], ensure_ascii=False)) > 5000:
            break
        page.append(item)
    actor.catalog_loaded = True
    return json.dumps({"total_purchasable_products": len(rows), "categories": dict(categories),
                       "price_range_yuan": [min(prices), max(prices)] if prices else [],
                       "offset": offset, "next_offset": offset + len(page) if offset + len(page) < len(rows) else None,
                       "products": page,
                       "notice": "仅本店在售且有货商品，分页或规格列表可能截断；推荐前须按需求重新筛选，预算小计不含运费。"}, ensure_ascii=False)


def product_results(keyword=None, reason=None, product_id=None, budget_yuan=None, limit=3,
                    requirements="", category=None, keywords=None, excluded_keywords=None,
                    min_price_yuan=None, quantity=1):
    db, actor = current()
    products = db.scalars(_product_query().where(Product.shop_id == actor.shop_id)).unique().all()
    if actor.role != "merchant" or reason:
        products = [product for product in products if listed_on_c(product)]
    if keyword:
        products = [product for product in products if keyword in product.name or keyword in product.category]
    if reason in ("related", "viewed"):
        ids = [product_id] if reason == "related" else _recent_ids(actor.user_id)
        reference = next((product for reference_id in ids for product in products if product.id == reference_id), None)
        if reason == "related" and reference is None:
            return "没有找到可用于推荐的商品。"
        if reference:
            products = [product for product in products if product.category == reference.category and product.id != reference.id]
    rows = [serialize_product(product, audience="b" if actor.role == "merchant" and not reason else "c") for product in products]
    if reason:
        filtered = []
        for row in rows:
            if category and row["category"] != category:
                continue
            if row["limit_per_user"] and quantity > row["limit_per_user"]:
                continue
            product_text = " ".join((row["name"], row["category"], row["description"])).casefold()
            sku_terms = {term.casefold() for term in (keywords or []) + (excluded_keywords or [])
                         if any(term.casefold() in sku["spec"].casefold() for sku in row["skus"])}
            matching_skus = []
            for sku in row["skus"]:
                searchable = product_text + " " + sku["spec"].casefold()
                if sku["stock"] < quantity:
                    continue
                if budget_yuan is not None and round(sku["price_yuan"] * quantity, 2) > budget_yuan:
                    continue
                if min_price_yuan is not None and sku["price_yuan"] < min_price_yuan:
                    continue
                if not all(term.casefold() in (sku["spec"].casefold() if term.casefold() in sku_terms else searchable) for term in keywords or []):
                    continue
                if any(term.casefold() in (sku["spec"].casefold() if term.casefold() in sku_terms else searchable) for term in excluded_keywords or []):
                    continue
                matching_skus.append(sku)
            if matching_skus:
                row["skus"] = matching_skus
                row["price_from"] = min(sku["price_yuan"] for sku in matching_skus)
                filtered.append(row)
        rows = filtered
    if reason:
        rows.sort(key=lambda row: (-row["sales_count"], row["id"]))
    rows = rows[:limit]
    if reason:
        actor.products.clear()
    actor.products.extend(rows)
    if not rows:
        return "没有找到在售商品或符合条件的商品。" if actor.role != "merchant" or reason else "没有找到本店商品。"
    prefix = f"需求摘要：{requirements[:500]}\n" if requirements else ""
    if reason:
        prefix += f"已按本店在售、有货、数量{quantity}及提供的条件筛选；小计不含运费，未校验用户累计限购剩余额度。\n"
    return prefix + "本店商品：\n" + "\n".join(
        f"{row['name']}（商品id {row['id']}，{row['category']}，{row['status']}）："
        + "；".join(f"{sku['spec']}（SKU {sku['id']}） ¥{sku['price_yuan']:.2f} 库存{sku['stock']}" + (f"，{quantity}件小计¥{sku['price_yuan'] * quantity:.2f}" if reason else "") for sku in row["skus"])
        + (f"。商品说明：{row['description'][:300]}" if row["description"] else "")
        for row in rows
    )


def merchant_orders(order_no=None):
    db, actor = current()
    query = _orders().where(Order.shop_id == actor.shop_id)
    if order_no:
        query = query.where(Order.order_no == order_no)
    rows = db.scalars(query.order_by(Order.id.desc()).limit(5)).unique().all()
    return "\n".join(
        f"订单 {order.order_no}，{STATUS_LABELS.get(order.status, order.status)}，合计 ¥{yuan(order.total_cents):.2f}。商品："
        + "，".join(f"{item.product_name} {item.sku_spec} x{item.quantity}" for item in order.items)
        for order in rows
    ) or "没有找到这个订单。"


def merchant_overview():
    db, actor = current()
    products = db.scalar(select(func.count(Product.id)).where(Product.shop_id == actor.shop_id))
    orders = db.scalars(select(Order).where(Order.shop_id == actor.shop_id)).all()
    revenue = sum(order.total_cents for order in orders if order.status in ("paid", "shipped", "completed"))
    return f"本店商品 {products} 件，订单 {len(orders)} 单，已支付销售额 ¥{yuan(revenue):.2f}（含运费），待发货 {sum(order.status == 'paid' for order in orders)} 单。"


def low_inventory(threshold=5):
    db, actor = current()
    products = db.scalars(select(Product).options(joinedload(Product.skus)).where(Product.shop_id == actor.shop_id)).unique().all()
    rows = [f"{product.name} / {sku.spec}（SKU {sku.id}，{product.status}/{sku.status}）库存 {sku.stock}" for product in products for sku in product.skus if sku.stock <= threshold]
    return "\n".join(rows[:30]) or "本店暂无低库存 SKU。"
