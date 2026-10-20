import re

from app.agent.context import current
from app.agent.guard import execute_tool


def product_quick_reply(message):
    """Only explicit, standalone product facts qualify; always read live scoped tools."""
    text = message.strip()
    match = re.fullmatch(
        r"(?:请问|帮我查一下|查一下|查询)?([\u4e00-\u9fffA-Za-z0-9 ]{1,30}?)(?:还有货吗|有货吗|库存多少|库存|多少钱|价格多少|什么价格|价格)[？?！!。]*",
        text,
    )
    if not match:
        return
    keyword = match.group(1).strip()
    if any(word in keyword for word in ("这个", "那个", "刚才", "不要", "推荐", "订单", "退款", "退货", "政策", "修改", "调整", "便宜", "预算", "和", "与", "或", "比", "最")):
        return
    sku = re.fullmatch(r"SKU\s*(\d+)", keyword, re.IGNORECASE)
    tool = "check_inventory" if sku else "search_products"
    args = {"sku_id": int(sku.group(1))} if sku else {"keyword": keyword, "limit": 3}
    result = execute_tool(tool, args)
    if result.startswith(("工具执行失败", "没有找到", "参数", "不支持")):
        return
    return (result + "\n\n库存、价格以当前查询时刻为准，下单时再次校验。",
            [{"tool": tool, "args": args, "result": result}])


def product_preview(message):
    actor = current()[1]
    if actor.progress is None:
        return
    reply = product_quick_reply(message)
    if reply:
        actor.progress({"type": "preview", "answer": reply[0], "tool": reply[1][0]["tool"]})
