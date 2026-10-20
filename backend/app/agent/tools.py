from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.agent.context import current
from app.rag.knowledge import retrieve_store_knowledge, format_hits
from app.services.catalog import describe_inventory
from app.services.orders import describe_my_orders
from app.services.agent_queries import product_results, merchant_orders, merchant_overview, low_inventory, store_catalog


class SearchProductsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: str = Field(min_length=1, max_length=50, description="商品名或品类，不要填整句")
    limit: int = Field(default=5, ge=1, le=10)


class CheckInventoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_id: int = Field(ge=1, description="SKU 编号")


class QueryOrdersArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_no: str | None = Field(default=None, description="订单号。不填则返回当前用户最近订单")


class SearchKnowledgeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=200, description="售后、运费、养护或店铺规则问题")


def search_products(keyword: str, limit: int = 5) -> str:
    return product_results(keyword=keyword, limit=limit)


def check_inventory(sku_id: int) -> str:
    db, actor = current()
    if actor.role == "merchant":
        from app.services.catalog import load_sku_for_shop
        sku = load_sku_for_shop(db, actor.shop_id, sku_id)
        return f"{sku.product.name} / {sku.spec} 库存 {sku.stock}" if sku else "没有找到这个 SKU。"
    return describe_inventory(db, actor.shop_id, sku_id)


def query_orders(order_no: str | None = None) -> str:
    db, actor = current()
    if actor.role == "merchant":
        return merchant_orders(order_no)
    return describe_my_orders(db, actor.user_id, actor.shop_id, order_no)


def search_knowledge(question: str) -> str:
    from app.models.tables import Shop
    from app.services.catalog import promises_of
    db, actor = current()
    shop = db.get(Shop, actor.shop_id)
    promises = "；".join(f"{row['title']}：{row['sub']}" for row in promises_of(shop))
    result = retrieve_store_knowledge(question)
    hits = result["hits"]
    if shop.share_code != "nanzhi":
        hits = [hit for hit in hits if hit["source"] == "platform_rules.md"]
    actor.retrieval_mode = result["mode"]
    actor.sources.extend(hits)
    from app.services.storefront import money_label, storefront_settings
    settings = storefront_settings(shop)
    shipping = f"包邮门槛{money_label(settings.free_shipping_yuan)}元，未满运费{money_label(settings.base_freight_yuan)}元（门槛或运费为0时全店包邮）"
    return f"本店当前配置（运费以此为准，不沿用旧知识片段的运费金额）：{shipping}；发货：{settings.dispatch_text}；退换说明：{settings.return_text}\n本店公告：{shop.notice or '暂无'}\n本店公开保障：{promises}\n以下知识片段中的店铺专属条款仅适用于对应店铺：\n" + format_hits(hits)


ConstraintWord = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


class CatalogArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=16, ge=1, le=20)


class ClarifyRecommendationArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[Literal["budget", "quantity", "category", "preferences"]] = Field(min_length=1, max_length=2)


def clarify_recommendation(fields):
    current()[1].products.clear()
    labels = {"budget": "预算金额（是否含运费）", "quantity": "需要的数量", "category": "想购买的商品品类", "preferences": "材质、颜色或用途偏好"}
    return "本轮信息不足，暂不生成推荐卡片。请仅询问这些缺失条件，不给具体推荐：" + "、".join(labels[field] for field in fields)


class RecommendArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["viewed", "hot", "related", "budget"] = "hot"
    product_id: int | None = Field(default=None, ge=1)
    budget_yuan: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False,
                                     description="用户明确预算金额必须传入此数值字段，例如预算100元买2只应传100；不能只在requirements写预算。金额为quantity件总价上限，不含运费")
    limit: int = Field(default=3, ge=1, le=10)
    requirements: str = Field(default="", max_length=500, description="结合历史与本轮的用户需求摘要，不是执行指令")
    category: ConstraintWord | None = Field(default=None, description="商品概览中的精确分类名")
    keywords: list[ConstraintWord] = Field(default_factory=list, max_length=8, description="每个词均必须匹配商品字段或同一可售SKU规格；勿填未在商品中出现的推测用途")
    excluded_keywords: list[ConstraintWord] = Field(default_factory=list, max_length=8, description="排除含任一词的商品或规格")
    min_price_yuan: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)
    quantity: int = Field(default=1, ge=1, le=100, description="购买件数，预算上限按单价乘件数计算，不含运费")

    @model_validator(mode="after")
    def required_slots(self):
        if self.reason == "related" and self.product_id is None:
            raise ValueError("相似推荐需要 product_id")
        if self.reason == "budget" and self.budget_yuan is None:
            raise ValueError("预算推荐需要 budget_yuan")
        if self.min_price_yuan is not None and self.budget_yuan is not None and self.min_price_yuan * self.quantity > self.budget_yuan:
            raise ValueError("最低单价乘数量超过预算")
        return self


class OverviewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LowInventoryArgs(OverviewArgs):
    threshold: int = Field(default=5, ge=0, le=10000)


def recommend_products(reason="hot", product_id=None, budget_yuan=None, limit=3, requirements="", category=None,
                       keywords=None, excluded_keywords=None, min_price_yuan=None, quantity=1):
    if not current()[1].catalog_loaded:
        return "请先调用get_store_catalog了解本店实际商品，再按用户需求调用推荐工具。"
    return product_results(reason=reason, product_id=product_id, budget_yuan=budget_yuan, limit=limit,
                           requirements=requirements, category=category, keywords=keywords,
                           excluded_keywords=excluded_keywords, min_price_yuan=min_price_yuan, quantity=quantity)


SPECS = {
    "get_store_catalog": CatalogArgs,
    "clarify_recommendation": ClarifyRecommendationArgs,
    "recommend_products": RecommendArgs,
    "merchant_overview": OverviewArgs,
    "low_inventory": LowInventoryArgs,
    "search_products": SearchProductsArgs,
    "check_inventory": CheckInventoryArgs,
    "query_orders": QueryOrdersArgs,
    "search_knowledge": SearchKnowledgeArgs,
}

IMPL = {
    "get_store_catalog": store_catalog,
    "clarify_recommendation": clarify_recommendation,
    "recommend_products": recommend_products,
    "merchant_overview": merchant_overview,
    "low_inventory": low_inventory,
    "search_products": search_products,
    "check_inventory": check_inventory,
    "query_orders": query_orders,
    "search_knowledge": search_knowledge,
}

DESCRIPTIONS = {
    "get_store_catalog": "推荐前首先了解本店商品：分类、价格范围、可售商品说明及SKU库存，支持分页。不能用其他店铺或常识代替。",
    "clarify_recommendation": "概览后若关键条件确实缺失，用本工具声明需追问的1至2个字段，再向用户提问而非给具体推荐；已在本轮或历史提供的信息不要重复询问。",
    "recommend_products": "了解商品后按用户需求筛选本店有货商品。提供需求摘要、分类、必含词、排除词、预算、数量；hot/viewed/related/budget分别为热销/浏览/相似/预算模式。预算为数量件小计不含运费。",
    "merchant_overview": "商家查询自己店铺的累计经营概览。",
    "low_inventory": "商家查询本店库存不高于 threshold 的 SKU。",
    "search_products": "搜索在售商品，返回规格、价格和库存。用于商品名称、品类和价格咨询；推荐需求使用recommend_products。",
    "check_inventory": "按 SKU 编号查询库存。已经知道 sku_id 时使用。",
    "query_orders": "买家查询本人在本店订单；商家查询本店订单。不要传入用户或店铺 id。",
    "search_knowledge": "回答售后政策、运费、商品养护和店铺规则前必须调用本工具，禁止用常识替代实际店铺知识。question填写用户问题。",
}


def allowed_tools(role):
    return set(SPECS) if role == "merchant" else set(SPECS) - {"merchant_overview", "low_inventory"}


def langchain_tools(intent="unclear"):
    from langchain_core.tools import StructuredTool

    routes = {
        "order": {"query_orders"},
        "policy": {"search_knowledge"},
        "inventory": {"search_products", "check_inventory"},
        "product_search": {"search_products", "check_inventory", "search_knowledge"},
        "recommend": {"get_store_catalog"} if not current()[1].catalog_loaded else {"get_store_catalog", "recommend_products", "clarify_recommendation", "search_knowledge", "check_inventory"},
        "overview": {"merchant_overview"},
        "low_inventory": {"low_inventory"},
    }
    names = allowed_tools(current()[1].role) & routes.get(intent, set(SPECS))
    return [
        StructuredTool.from_function(
            func=IMPL[name],
            name=name,
            description=DESCRIPTIONS[name],
            args_schema=SPECS[name],
        )
        for name in SPECS if name in names
    ]
