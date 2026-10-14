from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.agent.context import current
from app.models.tables import Order, Product
from app.services.catalog import _product_query, serialize_product, yuan
from app.services.engagement import _recent_ids
from app.services.orders import STATUS_LABELS, _orders
from app.services.shelf import listed_on_c


def product_results(keyword=None, reason=None, product_id=None, budget_yuan=None, limit=3):
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
    if budget_yuan is not None:
        rows = [row for row in rows if row["price_from"] is not None and row["price_from"] <= budget_yuan]
    if reason:
        rows.sort(key=lambda row: (-row["sales_count"], row["id"]))
    rows = rows[:limit]
    actor.products.extend(rows)
    if not rows:
        return "没有找到在售商品或符合条件的商品。" if actor.role != "merchant" or reason else "没有找到本店商品。"
    return "本店商品：\n" + "\n".join(
        f"{row['name']}（商品id {row['id']}，{row['category']}，{row['status']}）："
        + "；".join(f"{sku['spec']}（SKU {sku['id']}） ¥{sku['price_yuan']:.2f} 库存{sku['stock']}" for sku in row["skus"])
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
