import re


def classify(message):
    scope_text = re.sub(r"(?:不要|无需|禁止|不能|不想|不需要|别)(?:再)?(?:搜索|查询|查找|查看|获取|列出|展示)(?:一下|下)?(?:其他|其它|别家|别的)店(?:铺)?", "", message)
    if re.search(r"(?:搜索|查询|查找|查看|获取|列出|展示)(?:一下|下)?(?:其他|其它|别家|别的)店(?:铺)?", scope_text) or re.search(r"(?:给我|展示|获取|列出)跨店商品卡", scope_text):
        return "foreign_shop"
    # “不要推荐”是约束，不应把明确搜索错误分流到推荐工具。
    message = re.sub(r'(?:不要|不|无需)推荐', '', message)
    if re.search(r"(?:怎么|如何|哪里|步骤).*(?:配置|设置|新建|创建|添加商品|加商品|发券|发放|装修|上架)|(?:后台|B端).*(?:怎么|如何)", message):
        return "merchant_help"
    if any(word in message for word in ("购物车", "优惠券", "评论", "评价", "买家反馈", "店铺公告", "装修配置")):
        return "store_data"
    if re.search(r"(?:重新.*(?:生成|创建).*?(?:提案|草稿)|(?:提案|草稿).*重新.*生成|生成.*商品.*提案)", message):
        return "product_write"
    if any(word in message for word in ("配置商品", "生成商品", "创建商品", "新建商品", "复制商品", "商品草稿", "配置一个", "配置一款", "上新", "帮我卖", "新增商品")):
        return "product_write"
    if any(word in message for word in ("推荐", "挑选", "帮我选", "怎么选", "选哪个", "送礼", "送朋友", "礼物", "送给", "便宜一点", "换一个", "换一款", "不要这个", "更便宜")) or re.search(r"(?:换|改|不要|只要).*(?:色|材质|款式|款型)", message):
        return "recommend"
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
    if re.search(r"(?:我想|我需要|我要|帮我找|想买).*(?:睡觉|睡前|卧室|客厅|厨房|办公|收纳|喝茶|喝水|记笔记|写日记).*(?:东西|用品|用的|适合|商品)", message):
        return "recommend"
    if any(word in message for word in ("商品", "搜索", "买", "有没有", "价格", "多少钱", "抱枕", "杯", "蜡烛", "收纳")):
        return "product_search"
    return "unclear"
