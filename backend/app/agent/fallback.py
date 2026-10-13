import re

from app.agent.guard import execute_tool

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
        keyword = extract_keyword(message)
        if len(keyword) < 1:
            answer = "请告诉我商品名称，例如抱枕或马克杯。"
            return answer, []
        args = {"keyword": keyword}
        result = execute_tool("search_products", args)
        return result, [{"tool": "search_products", "args": args, "result": result}]
    answer = "我可以查在售商品、库存和你自己的订单，也可以回答退货、运费和养护问题。"
    return answer, []
