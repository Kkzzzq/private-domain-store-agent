import re


def classify(message):
    if any(word in message for word in ("退款", "退货", "售后", "运费", "政策", "养护", "清洗", "规则", "包邮", "定制品", "保修")):
        return "policy"
    if re.search(r"PS\d{8,}", message.upper()) or any(word in message for word in ("订单", "物流", "发货", "到哪")):
        return "order"
    if any(word in message for word in ("经营", "销售额", "概览")):
        return "overview"
    if "预警" in message or "低库存" in message:
        return "low_inventory"
    if any(word in message for word in ("推荐", "预算", "热销", "相似")) or re.search(r"\d+(?:\.\d+)?\s*(?:元|块)\s*(?:以内|以下)", message):
        return "recommend"
    if any(word in message for word in ("库存", "有货", "还有")):
        return "inventory"
    if any(word in message for word in ("商品", "搜索", "买", "有没有", "价格", "多少钱", "抱枕", "杯", "蜡烛", "收纳")):
        return "product_search"
    return "unclear"
