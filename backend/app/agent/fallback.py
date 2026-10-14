import re

from app.agent.guard import execute_tool
from app.agent.intent import classify

POLICY_WORDS = ("退货", "退款", "售后", "运费", "包邮", "政策", "规则", "七天", "清洗", "养护", "保修", "定制品")
INVENTORY_WORDS = ("库存", "有货", "还有")
SEARCH_WORDS = ("推荐", "搜索", "买", "商品", "有没有", "价格", "多少钱", "抱枕", "杯", "蜡烛", "收纳")
ORDER_WORDS = ("订单", "物流", "发货", "到哪")
STOP_WORDS = (
    "请问",
    "你好",
    "我想",
    "想买",
    "有没有",
    "还有货吗",
    "还有吗",
    "还有",
    "库存",
    "有货",
    "推荐",
    "搜索",
    "一下",
    "商品",
    "价格",
    "多少钱",
    "吗",
    "呢",
    "的",
)


def extract_keyword(text: str) -> str:
    cleaned = text
    for word in STOP_WORDS:
        cleaned = cleaned.replace(word, "")
    cleaned = cleaned.strip(" ，,。！？?、")
    return cleaned[:20]


def fallback_reply(message: str) -> tuple[str, list[dict]]:
    if any(word in message for word in ("帮我发货", "帮我退款", "修改价格", "调整库存", "帮我上架", "帮我下架", "修改库存")):
        return "助手提供查询服务。请前往商品或订单页面完成修改、发货或售后操作。", []
    intent = classify(message)
    if intent in ("overview", "low_inventory", "recommend"):
        args = {}
        name = {"overview": "merchant_overview", "low_inventory": "low_inventory", "recommend": "recommend_products"}[intent]
        if intent == "recommend":
            budget = re.search(r"(?:预算\s*|)(\d+(?:\.\d+)?)\s*(?:元|块|以内|以下)", message)
            related = re.search(r"(?:商品\s*|id\s*)(\d+)", message, re.I)
            args = {"reason": "viewed" if "浏览" in message or "再推荐" in message else "hot"}
            if "相似" in message:
                if not related:
                    return "请提供要查相似款的商品编号。", []
                args = {"reason": "related", "product_id": int(related.group(1))}
            if budget:
                args = {"reason": "budget", "budget_yuan": float(budget.group(1))}
            elif "预算" in message:
                return "请告诉我预算金额，例如预算 100 元。", []
        result = execute_tool(name, args)
        return result, [{"tool": name, "args": args, "result": result}]
    order_no = re.search(r"PS\d{8,}", message.upper())
    if order_no or any(word in message for word in ORDER_WORDS):
        args = {"order_no": order_no.group(0)} if order_no else {}
        result = execute_tool("query_orders", args)
        return result, [{"tool": "query_orders", "args": args, "result": result}]
    if any(word in message for word in POLICY_WORDS):
        args = {"question": message[:200]}
        result = execute_tool("search_knowledge", args)
        return result, [{"tool": "search_knowledge", "args": args, "result": result}]
    if any(word in message for word in INVENTORY_WORDS) or any(word in message for word in SEARCH_WORDS):
        sku = re.search(r"SKU\s*(\d+)", message, re.I)
        if sku:
            args = {"sku_id": int(sku.group(1))}
            result = execute_tool("check_inventory", args)
            return result, [{"tool": "check_inventory", "args": args, "result": result}]
        keyword = extract_keyword(message)
        if len(keyword) < 1:
            answer = "请告诉我商品名称，例如抱枕或马克杯。"
            return answer, []
        args = {"keyword": keyword}
        result = execute_tool("search_products", args)
        return result, [{"tool": "search_products", "args": args, "result": result}]
    answer = "我可以查在售商品、库存和你自己的订单，也可以回答退货、运费和养护问题。"
    return answer, []
