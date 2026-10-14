from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.context import current
from app.rag.knowledge import search_store_knowledge
from app.services.catalog import describe_inventory
from app.services.orders import describe_my_orders
from app.services.agent_queries import product_results, merchant_orders, merchant_overview, low_inventory


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
    return f"本店公告：{shop.notice or '暂无'}\n本店公开保障：{promises}\n以下为公共示例知识，涉及南枝手作的条款仅适用于该店，其他店铺请以店铺公告及商家确认为准：\n" + search_store_knowledge(question)


class RecommendArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["viewed", "hot", "related", "budget"] = "hot"
    product_id: int | None = Field(default=None, ge=1)
    budget_yuan: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)
    limit: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def required_slots(self):
        if self.reason == "related" and self.product_id is None:
            raise ValueError("相似推荐需要 product_id")
        if self.reason == "budget" and self.budget_yuan is None:
            raise ValueError("预算推荐需要 budget_yuan")
        return self


class OverviewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LowInventoryArgs(OverviewArgs):
    threshold: int = Field(default=5, ge=0, le=10000)


def recommend_products(reason="hot", product_id=None, budget_yuan=None, limit=3):
    return product_results(reason=reason, product_id=product_id, budget_yuan=budget_yuan, limit=limit)


SPECS = {
    "recommend_products": RecommendArgs,
    "merchant_overview": OverviewArgs,
    "low_inventory": LowInventoryArgs,
    "search_products": SearchProductsArgs,
    "check_inventory": CheckInventoryArgs,
    "query_orders": QueryOrdersArgs,
    "search_knowledge": SearchKnowledgeArgs,
}

IMPL = {
    "recommend_products": recommend_products,
    "merchant_overview": merchant_overview,
    "low_inventory": low_inventory,
    "search_products": search_products,
    "check_inventory": check_inventory,
    "query_orders": query_orders,
    "search_knowledge": search_knowledge,
}

DESCRIPTIONS = {
    "recommend_products": "推荐本店在售商品：hot 热销、viewed 浏览偏好、related 相似商品、budget 预算内。",
    "merchant_overview": "商家查询自己店铺的累计经营概览。",
    "low_inventory": "商家查询本店库存不高于 threshold 的 SKU。",
    "search_products": "搜索在售商品，返回规格、价格和库存。用户问商品、推荐或价格时使用。",
    "check_inventory": "按 SKU 编号查询库存。已经知道 sku_id 时使用。",
    "query_orders": "买家查询本人在本店订单；商家查询本店订单。不要传入用户或店铺 id。",
    "search_knowledge": "检索售后政策、运费、商品养护和私域店铺规则。",
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
        "recommend": {"recommend_products", "search_products"},
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
