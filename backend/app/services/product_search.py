import json
from hashlib import sha256
from pathlib import Path

from filelock import FileLock

from app.core.config import settings
from app.core.logging import logger


SYNONYMS = (("被子", "棉被", "被芯", "羽绒被", "冬被", "夏被", "空调被"),
            ("马克杯", "马克杯"), ("抱枕", "靠枕"), ("收纳筐", "收纳篮"))


def product_text(row):
    return json.dumps({key: row.get(key) for key in ("name", "category", "description", "tags")}, ensure_ascii=False)


def sku_text(sku):
    return json.dumps({key: sku.get(key) for key in ("spec", "parameters")}, ensure_ascii=False)


def literal_match(keyword, text):
    term = keyword.strip().casefold()
    terms = next((group for group in SYNONYMS if term in group), (term,))
    return any(candidate.casefold() in text.casefold() for candidate in terms)


def documents(rows):
    chunks = []
    for row in rows:
        for sku in row["skus"]:
            header = f"商品 {row['name']}；分类 {row['category']}；规格 {sku['spec']}\n"
            content = product_text(row) + "\n" + sku_text(sku)
            for offset in range(0, len(content), 1100):
                chunks.append({"id": f"p{row['id']}-s{sku['id']}-{offset}",
                               "content": header + content[offset:offset + 1200],
                               "source": str(row["id"]), "heading_path": str(sku["id"])})
    return chunks


def semantic_matches(keyword, rows, db, actor):
    from app.rag.cloud_embeddings import EmbeddingQuotaError
    from app.rag.knowledge import KnowledgeBase, create_embedder
    from app.rag.routing import candidates, cooling, mark_quota

    if not rows or settings.embedding_provider not in {"qwen", "zhipu"}:
        return set()
    scope = sha256((str(db.get_bind().url) + f":{actor.shop_id}:{actor.role}:product-v1").encode()).hexdigest()[:24]
    root = Path(settings.chroma_path) / "products" / scope
    root.mkdir(parents=True, exist_ok=True)
    chunks = documents(rows)
    try:
        with FileLock(str(root / "index.lock"), timeout=30):
            for model in candidates():
                if cooling(model):
                    continue
                embedder = create_embedder(model)
                version = sha256((settings.embedding_provider + ":" + settings.cloud_embedding_base_url + ":" + model + ":" + embedder.input_version).encode()).hexdigest()[:24]
                base = KnowledgeBase(root, "products_" + version)
                try:
                    base.rebuild(chunks, embedder)
                    hits = base.semantic_search(keyword, embedder, k=12)
                except EmbeddingQuotaError:
                    mark_quota(model)
                    continue
                actor.embedding_model = model
                distances = {}
                for hit in hits:
                    pair = (int(hit["source"]), int(hit["heading_path"]))
                    distances[pair] = min(distances.get(pair, 2), hit["distance"])
                return distances
        raise RuntimeError("商品Embedding候选模型均不可用")
    except Exception as exc:
        if settings.rag_require_vectors:
            raise RuntimeError("商品语义检索未完成，不能据此断言没有商品") from exc
        logger.warning("商品语义检索不可用，保留完整字段字面搜索：%s", type(exc).__name__)
        return set()


def search_rows(keyword, rows, db, actor):
    matches = []
    for row in rows:
        common = literal_match(keyword, product_text(row))
        skus = [sku for sku in row["skus"] if common or literal_match(keyword, sku_text(sku))]
        if skus:
            matches.append({**row, "skus": skus})
    if matches:
        return matches
    pairs = semantic_matches(keyword, rows, db, actor)
    found = [{**row, "skus": [sku for sku in row["skus"] if (row["id"], sku["id"]) in pairs]}
             for row in rows if any((row["id"], sku["id"]) in pairs for sku in row["skus"])]
    if isinstance(pairs, dict):
        found.sort(key=lambda row: min(pairs[(row["id"], sku["id"])] for sku in row["skus"]))
    return found
