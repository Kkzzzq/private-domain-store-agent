from pydantic import BaseModel, ConfigDict, Field

from app.agent.context import current
from app.rag.knowledge import search_store_knowledge
from app.services.catalog import describe_inventory, search_on_sale
from app.services.orders import describe_my_orders


class SearchProductsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    keyword: str = Field(min_length=1, max_length=50, description="商品名或品类，不要填整句")
    limit: int = Field(default=5, ge=1, le=10)


class CheckInventoryArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku_id: int = Field(ge=1, description="SKU 编号")


class QueryOrdersArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_no: str | None = Field(default=None, description="订单号。不填则返回当前用户最近订单")


class SearchKnowledgeArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str = Field(min_length=2, max_length=200, description="售后、运费、养护或店铺规则问题")


def search_products(keyword: str, limit: int = 5) -> str:
    db, actor = current()
    return search_on_sale(db, actor.shop_id, keyword, limit)


def check_inventory(sku_id: int) -> str:
    db, actor = current()
    return describe_inventory(db, actor.shop_id, sku_id)


def query_orders(order_no: str | None = None) -> str:
    db, actor = current()
    return describe_my_orders(db, actor.user_id, actor.shop_id, order_no)


def search_knowledge(question: str) -> str:
    return search_store_knowledge(question)


SPECS = {
    "search_products": SearchProductsArgs,
    "check_inventory": CheckInventoryArgs,
    "query_orders": QueryOrdersArgs,
    "search_knowledge": SearchKnowledgeArgs,
}

IMPL = {
    "search_products": search_products,
    "check_inventory": check_inventory,
    "query_orders": query_orders,
    "search_knowledge": search_knowledge,
}

DESCRIPTIONS = {
    "search_products": "搜索在售商品，返回规格、价格和库存。用户问商品、推荐或价格时使用。",
    "check_inventory": "按 SKU 编号查询库存。已经知道 sku_id 时使用。",
    "query_orders": "查询当前登录用户自己的订单。不要传入其他用户的 id。",
    "search_knowledge": "检索售后政策、运费、商品养护和私域店铺规则。",
}


def langchain_tools():
    from langchain_core.tools import StructuredTool

    return [
        StructuredTool.from_function(
            func=IMPL[name],
            name=name,
            description=DESCRIPTIONS[name],
            args_schema=SPECS[name],
        )
        for name in SPECS
    ]
