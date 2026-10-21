import re


LABEL = r"(?:参考资料|参考来源|引用来源|资料来源|数据来源|信息来源|知识来源|检索来源|来源|Sources?|References?)"
FILE = r"[A-Za-z0-9_.\-/\\]+\.(?:md|txt|pdf|json|ya?ml|py|js|tsx?|csv|sql)(?:#[\w-]+)?"
TERMS = (("知识库", "店铺资料"), ("关键词检索", "查询"), ("语义检索", "查询"),
         ("向量检索", "查询"), ("向量索引", "店铺资料"), ("检索", "查询"))


def user_facing_answer(text):
    value = str(text or "").replace("\r\n", "\n")
    output, source_block = [], False
    citation = bool(re.search(FILE, value, re.I))
    for line in value.split("\n"):
        plain = re.sub(r"^\s*(?:#{1,6}\s*|>\s*|[-*+]\s+|\d+[.)]\s+)", "", line).replace("**", "").strip()
        if re.fullmatch(LABEL + r"\s*(?:[（(][^）)\n]*[）)])?\s*(?:[:：].*)?", plain, re.I):
            source_block, citation = True, True
            continue
        entry = bool(re.search(FILE, plain, re.I) or re.match(r"^(?:\[\^?\d+\]:|https?://|\[[^\]]+\]\(https?://)", plain))
        if source_block and (not plain or entry):
            continue
        source_block = False
        line = re.sub(r"[（(]\s*" + LABEL + r"\s*(?:[:：]|[（(])[^\n]*?[）)]", "", line, flags=re.I)
        line = re.sub(r"【[^】\n]*" + FILE + r"[^】\n]*】", "", line, flags=re.I)
        line = re.sub(r"(?<![\w\u4e00-\u9fff])" + LABEL + r"\s*(?:[（(][^）)\n]*[）)])?\s*[:：][^\n]*", "", line, flags=re.I)
        line = re.sub(r"\[[^\]\n]*\]\([^\s)]*\.(?:md|txt|pdf|json|ya?ml|py|js|tsx?|csv|sql)(?:#[^)]*)?\)", "", line, flags=re.I)
        line = re.sub(FILE, "店铺规则", line, flags=re.I)
        if citation:
            line = re.sub(r"\[\^?\d+\]", "", line)
        for term, replacement in TERMS:
            line = line.replace(term, replacement)
        output.append(line.rstrip())
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()
    return cleaned or "请告诉我您想了解的具体问题，我来帮您确认。"


def present_messages(messages):
    return [{**item, "content": user_facing_answer(item.get("content"))} if item.get("role") == "assistant" else dict(item)
            for item in messages]
