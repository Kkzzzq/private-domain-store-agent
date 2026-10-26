import re
import json

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
    from app.agent.context import current
    if classify(message) == "foreign_shop":
        return "我只能帮您查询本店的商品和服务，其他店铺的信息无法查看。您想了解本店哪类商品呢？", []
    if current()[1].role != "merchant":
        if classify(message) in ("product_write", "overview", "low_inventory", "merchant_help") or any(word in message for word in ("修改价格", "调整库存", "帮我上架", "帮我下架", "修改库存")):
            return "我在这里帮您选购商品和查询您自己的订单，店铺经营相关的问题可以联系商家。", []
        if any(word in message for word in ("添加商品", "加一个商品", "加个商品")):
            return "您想把哪件商品加入购物车呢？告诉我商品名称和想要的规格，我帮您找找。", []
    if any(word in message for word in ("帮我发货", "帮我退款", "修改价格", "调整库存", "帮我上架", "帮我下架", "修改库存")):
        return "助手提供查询服务。请前往商品或订单页面完成修改、发货或售后操作。", []
    intent = classify(message)
    if intent == "merchant_help":
        args = {"question": message[:200]}
        result = execute_tool("merchant_help", args)
        return result, [{"tool": "merchant_help", "args": args, "result": result}]
    if intent == "store_data":
        topic = "cart" if "购物车" in message else "coupons" if "优惠券" in message else "reviews" if any(word in message for word in ("评论", "评价", "反馈")) else "settings"
        args = {"topic": topic}
        result = execute_tool("query_store_data", args)
        try:
            rows = json.loads(result)["匹配记录"]
            if not rows:
                answer = "暂时没有找到相关记录。您可以告诉我具体商品或订单，我再帮您确认。"
            elif topic == "cart":
                answer = "您在本店的购物车里有：\n" + "\n".join(f"- {row['商品']} · {row['规格']} ×{row['数量']}，小计¥{row['商品小计']:.2f}" + ("（当前不可购买，请在购物车核对）" if not row["当前可购买"] else "") for row in rows)
            elif topic == "coupons":
                answer = "本店的优惠券情况：\n" + "\n".join(f"- {row['名称']}：满{row['门槛']}减{row['优惠金额']}，{row['本人领券状态']}。具体是否可用以结算页面为准。" for row in rows)
            elif topic == "reviews":
                answer = "找到这些反馈，供您参考，不代表每个人的体验：\n" + "\n".join(f"- {row.get('商品', row['类型'])}：{row.get('评价', row.get('内容', ''))}" for row in rows)
            else:
                answer = "本店公告：" + str(rows[0].get("公告") or "暂无新公告")
        except (ValueError, KeyError, TypeError):
            answer = "暂时没能确认相关信息，请稍后再试。"
        return answer, [{"tool": "query_store_data", "args": args, "result": result}]
    if intent == "product_write":
        return "当前使用规则查询，无法可靠生成商品配置。请切换智能模式后提供商品名称、规格、售价与库存，或前往商品管理新建草稿。不会自动创建或上架。", []
    if intent in ("overview", "low_inventory", "recommend"):
        args = {}
        name = {"overview": "merchant_overview", "low_inventory": "low_inventory", "recommend": "recommend_products"}[intent]
        if intent == "recommend":
            if any(word in message for word in ("不要", "不喜欢", "只要", "适合", "材质", "送", "排除", "便宜一点", "换一个", "陶瓷", "抱枕", "杯", "蜡烛", "棉麻", "两", "件", "只")):
                return "当前使用规则兜底，暂不能可靠解析材质、用途、数量和排除条件。请稍后使用智能推荐，或在商品页面按条件挑选；我不会忽略这些要求直接推荐热销商品。", []
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
        traces = []
        if intent == "recommend":
            catalog = execute_tool("get_store_catalog", {})
            traces.append({"tool": "get_store_catalog", "args": {}, "result": catalog})
        result = execute_tool(name, args)
        traces.append({"tool": name, "args": args, "result": result})
        return result, traces
    order_no = re.search(r"PS\d{8,}", message.upper())
    if order_no or any(word in message for word in ORDER_WORDS):
        args = {"order_no": order_no.group(0)} if order_no else {}
        result = execute_tool("query_orders", args)
        return result, [{"tool": "query_orders", "args": args, "result": result}]
    if any(word in message for word in POLICY_WORDS):
        args = {"question": message[:200]}
        result = execute_tool("search_knowledge", args)
        if current()[1].role != "merchant":
            from app.models.tables import Shop
            from app.services.storefront import money_label, storefront_settings
            db, actor = current()
            shop = db.get(Shop, actor.shop_id)
            config = storefront_settings(shop)
            if result.startswith(("工具执行失败", "不支持", "业务操作被拒绝")):
                answer = "暂时没能确认店铺规定，您可以联系商家帮您核实。"
            elif any(word in message for word in ("运费", "包邮")):
                answer = "本店当前全店包邮。" if config.free_shipping_yuan == 0 or config.base_freight_yuan == 0 else f"本店满{money_label(config.free_shipping_yuan)}元包邮，未满运费{money_label(config.base_freight_yuan)}元。"
            elif any(word in message for word in ("退货", "退款", "售后")):
                answer = f"本店退换说明：{config.return_text}。具体订单您可以在订单中心申请售后，或联系商家确认。"
            else:
                answer = "这个问题还需要商家帮您具体确认，您可以点击联系商家咨询。"
            return answer, [{"tool": "search_knowledge", "args": args, "result": result}]
        visible = re.sub(r"【[^\n]*】\s*", "", result)
        visible = visible.replace("以下知识片段中的店铺专属条款仅适用于对应店铺：", "")
        visible = re.sub(r"本店当前配置（[^）]*）", "本店当前设置", visible)
        return visible, [{"tool": "search_knowledge", "args": args, "result": result}]
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
