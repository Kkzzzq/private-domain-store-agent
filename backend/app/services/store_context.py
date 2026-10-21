import json
import re
from datetime import timezone, timedelta
from hashlib import sha256
from pathlib import Path

from filelock import FileLock
from sqlalchemy import select

from app.agent.context import current
from app.core.config import settings
from app.core.logging import logger
from app.models.tables import (Banner, CartItem, Coupon, CouponOrder, Order, Product, ProductTag, Review,
                               Section, Shop, ShopCategory, Testimonial, UserCoupon)
from app.services.shelf import listed_on_c


def clean_text(value):
    text = str(value or "")
    text = re.sub(r"(?<!\d)1\d{10}(?!\d)", "[手机号已隐藏]", text)
    return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已隐藏]", text)


def record(key, text, data):
    return {"id": str(key), "text": clean_text(text), "data": data}


def collect_records(db, actor, topic):
    from app.models.support import AfterSale, Shipment
    from app.services.catalog import promises_of, yuan
    from app.services.coupons import active, issuance_state
    from app.services.orders import STATUS_LABELS
    from app.services.storefront import storefront_settings

    merchant = actor.role == "merchant"
    shop = db.get(Shop, actor.shop_id)
    if not shop:
        return []
    from app.services.governance import shop_open
    if not merchant and topic in {"settings", "reviews", "coupons"} and not shop_open(shop):
        return []
    if topic == "merchant_help":
        if not merchant:
            return []
        from app.agent.merchant_manual import help_records
        return help_records()
    records = []
    if topic == "settings":
        config = storefront_settings(shop).model_dump()
        public = {key: config[key] for key in ("free_shipping_yuan", "base_freight_yuan", "dispatch_text", "return_text") if key in config}
        from app.services.assistant_identity import assistant_name
        data = {"店铺": shop.name, "Logo": shop.logo_url, "公告": shop.notice, "公开保障": promises_of(shop), "配置": config if merchant else public}
        if merchant:
            data["品牌与助手"] = {"助手名称": assistant_name(shop), "主题色": shop.theme_color, "轮播高度": shop.hero_height,
                               "浅色条纹": shop.strip_tint, "分享码": shop.share_code, "社交账号": shop.social_accounts, "营业状态": shop.status}
        records.append(record("shop", json.dumps(data, ensure_ascii=False), data))
        for model, label in ((Banner, "轮播图"), (Section, "商品栏目"), (Testimonial, "商家维护的展示反馈")):
            query = select(model).where(model.shop_id == actor.shop_id)
            if not merchant:
                query = query.where(model.enabled.is_(True))
            for item in db.scalars(query.order_by(model.sort_order, model.id)).all():
                data = {column.name: getattr(item, column.name) for column in model.__table__.columns if column.name not in {"shop_id", "nickname"}}
                if isinstance(item, Section):
                    data["product_ids"] = [entry.product_id for entry in item.items if merchant or (entry.product and listed_on_c(entry.product))]
                if not merchant:
                    data = {key: value for key, value in data.items() if key not in {"sort_order", "enabled", "source"}}
                records.append(record(f"{model.__tablename__}-{item.id}", label + json.dumps(data, ensure_ascii=False), {"类型": label, **data}))
        if merchant:
            for model, label in ((ShopCategory, "分类标签"), (ProductTag, "商品标签")):
                for item in db.scalars(select(model).where(model.shop_id == actor.shop_id)).all():
                    data = {column.name: getattr(item, column.name) for column in model.__table__.columns if column.name != "shop_id"}
                    if isinstance(item, ProductTag) and item.style_profile:
                        data["颜色配置"] = {key: getattr(item.style_profile, key) for key in ("background_color", "border_color", "text_color")}
                    records.append(record(f"{model.__tablename__}-{item.id}", label + json.dumps(data, ensure_ascii=False), data))
    elif topic == "coupons":
        owned = {row.coupon_id: row for row in db.scalars(select(UserCoupon).where(UserCoupon.user_id == actor.user_id)).all()}
        for coupon in db.scalars(select(Coupon).where(Coupon.shop_id == actor.shop_id).order_by(Coupon.id.desc())).all():
            own = owned.get(coupon.id)
            if not merchant and not active(coupon) and own is None:
                continue
            data = {"id": coupon.id, "名称": coupon.name, "门槛": yuan(coupon.threshold_cents), "优惠金额": yuan(coupon.amount_cents),
                    "开始": coupon.starts_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).isoformat(),
                    "结束": coupon.ends_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).isoformat(), "发放状态": issuance_state(coupon),
                    "本人领券状态": own.status if own else "未领取", "每单限用": 1, "不抵运费": True}
            if merchant:
                data.update({"发放总量": coupon.total_count, "已领取": coupon.claimed_count, "启用": coupon.enabled})
            records.append(record(coupon.id, f"优惠券 {coupon.name} 满{yuan(coupon.threshold_cents)}减{yuan(coupon.amount_cents)}", data))
    elif topic == "reviews":
        from app.models.governance import ReviewRestriction
        query = select(Review).join(Product, Product.id == Review.product_id).where(Product.shop_id == actor.shop_id)
        if not merchant:
            query = query.where(~Review.id.in_(select(ReviewRestriction.review_id).where(ReviewRestriction.hidden.is_(True))))
        for review in db.scalars(query.order_by(Review.id.desc())).all():
            if not merchant and not listed_on_c(review.product):
                continue
            data = {"类型": "真实购买评价", "商品": review.product.name, "product_id": review.product_id,
                    "sku_id": review.order_item.sku_id, "规格": review.order_item.sku_spec,
                    "评分": review.rating, "评价": clean_text(review.content)}
            records.append(record(review.id, json.dumps(data, ensure_ascii=False), data))
        for item in db.scalars(select(Testimonial).where(Testimonial.shop_id == actor.shop_id)).all():
            if item.enabled or merchant:
                data = {"类型": "商家维护的展示反馈（不是订单评价）", "评分": item.rating, "内容": clean_text(item.content)}
                records.append(record(f"testimonial-{item.id}", json.dumps(data, ensure_ascii=False), data))
    elif topic == "cart":
        query = select(CartItem).where(CartItem.shop_id == actor.shop_id, CartItem.user_id == actor.user_id)
        for item in db.scalars(query.order_by(CartItem.id.desc())).all():
            sku = item.sku
            if sku.product.shop_id != actor.shop_id:
                continue
            data = {"product_id": sku.product_id, "sku_id": sku.id, "商品": sku.product.name, "规格": sku.spec,
                    "数量": item.quantity, "单价": yuan(sku.price_cents), "商品小计": yuan(sku.price_cents * item.quantity),
                    "当前可购买": listed_on_c(sku.product) and sku.status == "on" and sku.stock >= item.quantity,
                    "图片": sku.image_url or sku.product.image_url}
            records.append(record(item.id, f"购物车 {sku.product.name} {sku.spec}", data))
    elif topic in {"orders", "aftersales"}:
        query = select(Order).where(Order.shop_id == actor.shop_id)
        if not merchant:
            query = query.where(Order.user_id == actor.user_id)
        for order in db.scalars(query.order_by(Order.id.desc())).all():
            items = [{"product_id": item.product_id, "sku_id": item.sku_id, "商品": item.product_name,
                      "规格": item.sku_spec, "数量": item.quantity, "下单单价": yuan(item.price_cents)} for item in order.items]
            shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
            after = db.scalar(select(AfterSale).where(AfterSale.order_id == order.id))
            if topic == "aftersales" and after is None:
                continue
            data = {"订单号": order.order_no, "状态": STATUS_LABELS.get(order.status, order.status), "合计": yuan(order.total_cents), "运费": yuan(order.freight_cents),
                    "创建时间": order.created_at.isoformat(), "商品": items}
            coupon = db.scalar(select(CouponOrder).where(CouponOrder.order_id == order.id))
            if coupon:
                data["订单优惠"] = {"券名": coupon.name, "抵扣": yuan(coupon.discount_cents), "状态": coupon.status}
            if shipment:
                data["物流"] = {"承运商": shipment.carrier, "状态": shipment.status, "单号": shipment.tracking_number}
            if after:
                data["售后"] = {"类型": after.kind, "状态": after.status, "原因": clean_text(after.reason),
                              "退回承运商": after.return_carrier, "退回单号": after.return_tracking}
            text = "订单商品 " + " ".join(item["商品"] + " " + item["规格"] for item in items)
            if after:
                tags = [term for term in ("破损", "尺寸", "颜色", "质量", "少件", "错发", "退款", "退货", "物流", "漏发") if term in after.reason]
                text += " 售后问题 " + " ".join(tags)
            records.append(record(order.id, text, data))
    return records


def ranked_ids(records, question, db, actor, topic, limit, build_only=False):
    order_numbers = re.findall(r"PS\d{8,}", question.upper()) if topic in {"orders", "aftersales"} else []
    if order_numbers:
        return [row["id"] for row in records if row["data"].get("订单号") in order_numbers][:limit]
    if not question.strip() and not build_only:
        return [row["id"] for row in records[:limit]]
    exact = [row["id"] for row in records if question.casefold() in row["text"].casefold() or question in str(row["data"].get("订单号", ""))]
    if exact and not build_only:
        return exact[:limit]
    from app.rag.knowledge import KnowledgeBase, create_embedder
    from app.rag.routing import candidates, cooling, mark_quota
    from app.rag.cloud_embeddings import EmbeddingQuotaError
    owner = actor.user_id if topic in {"cart", "orders", "aftersales", "coupons"} else 0
    scope = sha256((str(db.get_bind().url) + f":{actor.shop_id}:{actor.role}:{owner}:{topic}:v1").encode()).hexdigest()[:24]
    if settings.embedding_provider in {"qwen", "zhipu"} and records:
        root = Path(settings.chroma_path) / "context" / scope
        root.mkdir(parents=True, exist_ok=True)
        chunks = []
        for row in records:
            for offset in range(0, len(row["text"]), 1100):
                chunks.append({"id": f"{row['id']}-{offset}", "source": row["id"], "heading_path": topic, "content": row["text"][offset:offset + 1200]})
        try:
            with FileLock(str(root / "index.lock"), timeout=30):
                for model in candidates():
                    if cooling(model):
                        continue
                    embedder = create_embedder(model)
                    version = sha256((settings.embedding_provider + settings.cloud_embedding_base_url + model + embedder.input_version).encode()).hexdigest()[:24]
                    base = KnowledgeBase(root, "context_" + version)
                    try:
                        base.rebuild(chunks, embedder)
                        hits = [] if build_only else base.semantic_search(question, embedder, k=limit)
                    except EmbeddingQuotaError:
                        mark_quota(model)
                        continue
                    actor.embedding_model = model
                    return list(dict.fromkeys(hit["source"] for hit in hits))[:limit]
        except Exception as exc:
            if settings.rag_require_vectors:
                raise RuntimeError("本店数据语义检索未完成") from exc
            logger.warning("本店数据语义检索不可用：%s", type(exc).__name__)
    terms = {question[index:index + 2] for index in range(len(question) - 1)}
    scored = sorted(((sum(term in row["text"] for term in terms), row["id"]) for row in records), reverse=True)
    return [key for score, key in scored if score > 0][:limit]


def query_store_data(topic, question="", limit=5):
    db, actor = current()
    if topic == "merchant_help" and actor.role != "merchant":
        return "当前购物助手不提供后台操作指导。"
    if topic not in {"settings", "coupons", "reviews", "cart", "orders", "aftersales", "merchant_help"}:
        return "不支持的数据主题。"
    records = collect_records(db, actor, topic)
    selected = set(ranked_ids(records, question, db, actor, topic, limit))
    db.expire_all()
    fresh = collect_records(db, actor, topic)
    data = [row["data"] for row in fresh if row["id"] in selected][:limit]
    return json.dumps({"主题": topic, "匹配记录": data, "当前授权范围记录数": len(fresh),
                       "说明": "仅当前店铺与当前身份授权数据；实时SQL核验。评价不是效果保证，活动资格及最终应付以结算页面为准。"}, ensure_ascii=False)


def merchant_help(question, limit=3):
    result = query_store_data("merchant_help", question, limit)
    if current()[1].role != "merchant":
        return result
    rows = json.loads(result)["匹配记录"]
    return "\n\n".join(row["操作说明"] for row in rows) if rows else "暂时没找到对应功能的操作步骤，请说明想配置的页面或项目。"
