from hashlib import sha256


RAG_CASES = {"A15", "A16", "A35", "A36"}


def rag_case(case_id, chat, evidence):
    from app.core.config import settings
    from app.rag.knowledge import KnowledgeBase, create_embedder

    settings.rag_require_vectors = True
    if settings.cloud_api_style in {"qwen", "zhipu"}:
        settings.embedding_provider = settings.cloud_api_style
    settings.rag_max_distance = 0.65
    base = KnowledgeBase(settings.chroma_path)
    chunks = [{"id": "qa-policy", "source": "platform_rules.md", "heading_path": "测试延保", "content": "测试青柠陶杯专属延保政策：购买后37天内开裂可申请换新。延保不是普通退货政策，请联系商家核实。"}]
    if case_id == "A36":
        chunks.append({"id": "qa-conflict", "source": "platform_rules.md", "heading_path": "另一条未确认延保", "content": "测试青柠陶杯专属延保政策：购买后13天内开裂可申请换新。此条与37天政策冲突，两个版本均未指定优先级，必须联系商家核实，不可擅自选择一个。"})
    embedder = create_embedder()
    written = base.rebuild(chunks, embedder)
    evidence.check("真实Embedding写入独立Chroma", written == len(chunks) and base.has_vectors(), len(chunks), written)
    question = "测试青柠陶杯专属延保政策中，开裂多少天内可申请换新？请注明知识来源。"
    if case_id == "A16":
        settings.rag_max_distance = 0.0
        question = "平台政策是否承诺太空旅行事故保险？查知识库，无相关条款就明确说没有，不得编造。"
    if case_id == "A35":
        first = chat(question)
        evidence.check("初版政策确实检索到37天", first["retrieval_mode"] == "chroma" and any("37天" in row["content"] for row in first["sources"]))
        old_version = sha256(chunks[0]["content"].encode()).hexdigest()
        chunks[0]["content"] = chunks[0]["content"].replace("37天", "43天")
        base.rebuild(chunks, embedder)
        output = chat("请重新检索最新的测试青柠陶杯延保政策，多少天内开裂可申请换新？注明来源。", session=first["session_id"])
        evidence.check("更新后来源不含旧版本", bool(output["sources"]) and all(row["version"] != old_version and "37天" not in row["content"] for row in output["sources"]))
        evidence.check("回答使用更新政策", "43" in output["answer"] and "37天" not in output["answer"], "43天", output["answer"])
    else:
        output = chat(question)
    evidence.check("回答实际走Chroma不退回关键词", output["retrieval_mode"] == "chroma", "chroma", output["retrieval_mode"])
    if case_id == "A16":
        evidence.check("无命中无伪造引用", not output["sources"] and any(word in output["answer"] for word in ("没有", "未找到", "未查到", "未检索", "暂无")), None, output)
    else:
        evidence.check("每个知识来源包含可追溯块和版本", bool(output["sources"]) and all(row.get("chunk_id") and len(row.get("version", "")) == 64 for row in output["sources"]), None, output["sources"])
        if case_id == "A15":
            evidence.check("答案与真实检索政策一致且带来源", "37" in output["answer"] and "platform_rules.md" in output["answer"], None, output["answer"])
        if case_id == "A36":
            evidence.check("冲突政策不擅自取舍", len(output["sources"]) == 2 and any(word in output["answer"] for word in ("冲突", "不一致", "矛盾")) and "商家" in output["answer"], None, output)
    return {"pipeline": f"{settings.embedding_provider}_embedding→isolated_chroma→business_agent", "chunks": len(chunks), "max_distance": settings.rag_max_distance,
            "versions": [{"id": row["id"], "version": sha256(row["content"].encode()).hexdigest()} for row in chunks]}
