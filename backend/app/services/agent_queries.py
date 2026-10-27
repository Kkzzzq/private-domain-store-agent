import json
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.agent.context import current
from app.models.tables import Order, Product, Shop
from app.services.catalog import _product_query, serialize_product, yuan
from app.services.c_projection import serialize_c, sync_shop, view_rows
from app.services.engagement import _recent_ids
from app.services.orders import STATUS_LABELS, _orders


def _buyer_side_open(db, shop_id: int) -> bool:
    """买家侧与助手共用一条底线：店铺被冻结时一律看不到货。"""
    return db.scalar(select(Shop.status).where(Shop.id == shop_id)) == "open"


def _catalog_rows(db, actor, *, buyer_view: bool = False) -> list[dict]:
    """助手取数口径：买家（以及推荐场景）读 C 端宽表，商家看货读 SPU/SKU 权威表。"""
    if actor.role == "merchant" and not buyer_view:
        products = db.scalars(_product_query().where(Product.shop_id == actor.shop_id)).unique().all()
        return [serialize_product(product, audience="b") for product in products]
    if not _buyer_side_open(db, actor.shop_id):
        return []
    sync_shop(db, actor.shop_id)
    return [serialize_c(view) for view in view_rows(db, actor.shop_id, listed_only=True)]


def _reload_rows(db, actor, ids: set[int], *, buyer_view: bool = False) -> dict[int, dict]:
    """检索耗时之后重新取一次实时值，避免把检索前的旧价格带回回答。"""
    if not ids:
        return {}
    db.expire_all()
    if actor.role == "merchant" and not buyer_view:
        products = db.scalars(
            _product_query().where(Product.shop_id == actor.shop_id, Product.id.in_(ids))
        ).unique().all()
        return {product.id: serialize_product(product, audience="b") for product in products}
    if not _buyer_side_open(db, actor.shop_id):
        return {}
    sync_shop(db, actor.shop_id)
    views = view_rows(db, actor.shop_id, listed_only=True)
    return {view.spu_id: serialize_c(view) for view in views if view.spu_id in ids}


def store_catalog(offset=0, limit=16):
    db, actor = current()
    merchant = actor.role == "merchant"
    rows = _catalog_rows(db, actor)
    if not merchant:
        for row in rows:
            row["skus"] = [sku for sku in row["skus"] if sku["stock"] > 0]
        rows = [row for row in rows if row["skus"]]
    categories = Counter(row["category"] for row in rows)
    prices = [sku["price_yuan"] for row in rows for sku in row["skus"]]
    page = []
    for row in rows[offset:offset + limit]:
        item = {"id": row["id"], "spu_id": row["spu_id"], "name": row["name"], "category": row["category"],
                "status": row["status"], "image_url": row["image_url"],
                "description": row["description"][:120], "limit_per_user": row["limit_per_user"],
                "sku_count": len(row["skus"]), "sku_details_truncated": len(row["skus"]) > 4,
                "skus": [{key: sku[key] for key in ("id", "spec", "price_yuan", "stock", "status", "image_url", "parameters")} for sku in row["skus"][:4]]}
        if page and len(json.dumps(page + [item], ensure_ascii=False)) > 5000:
            break
        page.append(item)
    actor.catalog_loaded = True
    return json.dumps({"total_purchasable_products": len(rows), "categories": dict(categories),
                       "price_range_yuan": [min(prices), max(prices)] if prices else [],
                       "offset": offset, "next_offset": offset + len(page) if offset + len(page) < len(rows) else None,
                       "products": page,
                       "notice": "本店商家全量商品状态视图，不代表全部可购买；分页或SKU可能截断。" if merchant else "仅本店在售且有货商品，分页或规格列表可能截断；推荐前须按需求重新筛选，预算小计不含运费。"}, ensure_ascii=False)


def image_products(question, limit=3):
    from app.rag.product_images import search_product_images
    db, actor = current()
    merchant = actor.role == "merchant"
    rows = _catalog_rows(db, actor)
    pairs, state = search_product_images(question, rows, db, actor)
    ranks = {(item["product_id"], item["sku_id"]): index for index, item in enumerate(state.get("matching_assets", []))}
    fresh = _reload_rows(db, actor, {row["id"] for row in rows})
    candidates = []
    for row in fresh.values():
        row["skus"] = [sku for sku in row["skus"] if (row["id"], sku["id"]) in pairs or (row["id"], 0) in pairs]
        if row["skus"]:
            row["price_from"] = min(sku["price_yuan"] for sku in row["skus"])
            row["image_bindings"] = [{"product_id": row["id"], "sku_id": sku["id"],
                                      "image_url": sku["image_url"] or row["image_url"],
                                      "inherited_spu_image": not bool(sku["image_url"])} for sku in row["skus"]]
            specific = [sku for sku in row["skus"] if (row["id"], sku["id"]) in pairs]
            preferred = min(specific, key=lambda sku: ranks.get((row["id"], sku["id"]), 999), default=None)
            if preferred and preferred["image_url"]:
                row["spu_image_url"] = row["image_url"]
                row["image_url"] = preferred["image_url"]
            candidates.append(row)
    candidates.sort(key=lambda row: min((index for (product_id, sku_id), index in ranks.items() if product_id == row["id"]), default=999))
    candidates = candidates[:limit]
    actor.products.extend(candidates)
    return json.dumps({"图像索引": state, "候选商品": candidates, "说明": "图像语义相近仅为候选；不能仅凭图片保证材质功效或把相似外观当成相同规格。不可用时不能声称看过图片。"}, ensure_ascii=False)


def product_results(keyword=None, reason=None, product_id=None, budget_yuan=None, limit=3,
                    requirements="", category=None, keywords=None, excluded_keywords=None,
                    min_price_yuan=None, quantity=1, keyword_groups=None):
    if category:
        # An exact category already enforces its scope. Models sometimes add
        # its generic noun again as a literal keyword, hiding valid products.
        redundant = {category, category + "用品", category + "商品", category + "类商品"}
        keywords = [word for word in keywords or [] if word not in redundant]
    db, actor = current()
    buyer_view = actor.role != "merchant" or bool(reason)
    rows = _catalog_rows(db, actor, buyer_view=buyer_view)
    if reason in ("related", "viewed"):
        ids = [product_id] if reason == "related" else _recent_ids(actor.user_id)
        reference = next((row for row in rows if row["id"] in ids), None)
        if reason == "related" and reference is None:
            return "没有找到可用于推荐的商品。"
        if reference:
            rows = [row for row in rows if row["category"] == reference["category"] and row["id"] != reference["id"]]
    if keyword:
        from app.services.product_search import search_rows
        rows = search_rows(keyword, rows, db, actor)
        matched = {row["id"]: {sku["id"] for sku in row["skus"]} for row in rows}
        order = {product_id: index for index, product_id in enumerate(matched)}
        if matched:
            fresh = _reload_rows(db, actor, set(matched), buyer_view=buyer_view)
            rows = []
            for product_id, sku_ids in matched.items():
                row = fresh.get(product_id)
                if row is None:
                    continue
                row["skus"] = [sku for sku in row["skus"] if sku["id"] in sku_ids]
                if row["skus"]:
                    rows.append(row)
            rows.sort(key=lambda row: order[row["id"]])
        for row in rows:
            row["price_from"] = min((sku["price_yuan"] for sku in row["skus"]), default=None)
    if reason:
        filtered = []
        for row in rows:
            if category and row["category"] != category:
                continue
            if row["limit_per_user"] and quantity > row["limit_per_user"]:
                continue
            from app.services.product_search import product_text as searchable_product, sku_text
            product_text = searchable_product(row).casefold()
            alternatives = [term for group in keyword_groups or [] for term in group]
            sku_terms = {term.casefold() for term in (keywords or []) + (excluded_keywords or []) + alternatives
                         if any(term.casefold() in sku["spec"].casefold() for sku in row["skus"])}
            matching_skus = []
            for sku in row["skus"]:
                searchable = product_text + " " + sku_text(sku).casefold()
                if sku["stock"] < quantity:
                    continue
                if budget_yuan is not None and round(sku["price_yuan"] * quantity, 2) > budget_yuan:
                    continue
                if min_price_yuan is not None and sku["price_yuan"] < min_price_yuan:
                    continue
                if not all(term.casefold() in (sku["spec"].casefold() if term.casefold() in sku_terms else searchable) for term in keywords or []):
                    continue
                if not all(any(term.casefold() in (sku["spec"].casefold() if term.casefold() in sku_terms else searchable)
                               for term in group) for group in keyword_groups or []):
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
        return "没有找到在售商品或符合条件的商品。本次查询未命中不等于全店没有该品类，不能据此断言全店无相关商品。" if actor.role != "merchant" or reason else "没有找到本店商品。"
    prefix = f"需求摘要：{requirements[:500]}\n" if requirements else ""
    if keyword:
        prefix += "以下为完整字段或语义召回的候选，须核对名称、规格和说明是否确实满足用途；语义相近不代表用途相同，不把枕套当被子、花器当饮水杯。\n"
    if reason:
        prefix += f"已按本店在售、有货、数量{quantity}及提供的条件筛选；小计不含运费，未校验用户累计限购剩余额度。\n"
    return prefix + "本店商品：\n" + "\n".join(
        f"{row['name']}（商品id {row['id']}，{row['category']}，{row['status']}）："
        + "；".join(f"{sku['spec']}（SKU {sku['id']}） ¥{sku['price_yuan']:.2f} 库存{sku['stock']}" + (f"，参数{json.dumps(sku['parameters'], ensure_ascii=False)}" if sku.get("parameters") else "") + (f"，{quantity}件小计¥{sku['price_yuan'] * quantity:.2f}" if reason else "") for sku in row["skus"])
        + (f"。商品说明：{row['description'] if keyword else row['description'][:300]}" if row["description"] else "")
        + (f"。商品标签：{json.dumps(row['tags'], ensure_ascii=False)}" if keyword and row.get("tags") else "")
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
