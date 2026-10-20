from pathlib import Path

from app.core.config import settings
from app.core.logging import logger
from app.rag.cleaner import structured_chunks


class KnowledgeBase:
    def __init__(self, persist_dir: str | Path, collection: str | None = None) -> None:
        self.persist_dir = Path(persist_dir)
        self.collection = collection or settings.chroma_collection

    def load_chunks(self) -> list[dict]:
        chunks: list[dict] = []
        knowledge_dir = settings.knowledge_dir
        if not knowledge_dir.exists():
            return chunks
        for path in sorted(knowledge_dir.glob("*.md")):
            parts = structured_chunks(path.read_text(encoding="utf-8"))
            for index, part in enumerate(parts):
                chunks.append({"id": f"{path.stem}-{index}", **part, "source": path.name})
        return chunks

    def rebuild(self, chunks: list[dict], embedder) -> int:
        import chromadb

        self.persist_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self.persist_dir))
        vectors = embedder.embed_documents([f"{item.get('heading_path', '')}\n{item['content']}" for item in chunks]) if chunks else []
        model_name = getattr(embedder, "model_name", "custom")
        input_version = getattr(embedder, "input_version", "plain-v1")
        collection = client.get_or_create_collection(
            self.collection, metadata={"hnsw:space": "cosine", "embedding_model": model_name, "embedding_input_version": input_version}
        )
        if (collection.metadata or {}).get("embedding_model") != model_name:
            raise ValueError("Embedding 模型已改变，请使用新的 CHROMA_COLLECTION 重建")
        if (collection.metadata or {}).get("embedding_input_version", "plain-v1") != input_version:
            raise ValueError("Embedding输入格式已改变，请使用新的 CHROMA_COLLECTION 重建")
        if not chunks:
            existing = collection.get()["ids"]
            if existing:
                collection.delete(ids=existing)
            return 0
        collection.upsert(
            ids=[item["id"] for item in chunks],
            documents=[item["content"] for item in chunks],
            metadatas=[{"source": item["source"], "heading_path": item.get("heading_path", "正文")} for item in chunks],
            embeddings=vectors,
        )
        obsolete = set(collection.get()["ids"]) - {item["id"] for item in chunks}
        if obsolete:
            collection.delete(ids=list(obsolete))
        return len(chunks)

    def has_vectors(self) -> bool:
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(self.persist_dir))
            collection = client.get_collection(self.collection)
            return collection.count() > 0
        except Exception:
            return False

    def semantic_search(self, question: str, embedder, k: int = 3) -> list[dict]:
        import chromadb

        client = chromadb.PersistentClient(path=str(self.persist_dir))
        collection = client.get_collection(self.collection)
        model_name = getattr(embedder, "model_name", "custom")
        if (collection.metadata or {}).get("embedding_model") != model_name:
            raise ValueError("Embedding 模型与向量集合不一致，请重建索引")
        if (collection.metadata or {}).get("embedding_input_version", "plain-v1") != getattr(embedder, "input_version", "plain-v1"):
            raise ValueError("Embedding输入格式与向量集合不一致，请重建索引")
        total = collection.count()
        if total == 0:
            return []
        vector = embedder.embed_query(question)
        result = collection.query(query_embeddings=[vector], n_results=min(k, total))
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits = []
        for index, document in enumerate(documents):
            meta = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
            hits.append({"content": document, "source": meta.get("source", "chroma"), "heading_path": meta.get("heading_path", "正文"), "distance": distances[index] if index < len(distances) else None})
        return hits


def keyword_search(question: str, k: int = 3) -> list[dict]:
    scored: list[tuple[int, dict]] = []
    for item in KnowledgeBase(settings.chroma_path).load_chunks():
        score = _score(question, item["content"])
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:k]]


def _score(query: str, text: str) -> int:
    query = query.strip()
    if not query:
        return 0
    if query in text:
        return 100 + len(query)
    score = 0
    for index in range(len(query) - 1):
        if query[index : index + 2] in text:
            score += 1
    return score


def format_hits(hits: list[dict]) -> str:
    if not hits:
        return "没有找到相关的店铺规则或商品说明。"
    blocks = [f"【{hit['source']} / {hit.get('heading_path', '正文')}】\n{hit['content']}" for hit in hits]
    return "\n\n".join(blocks)


class OllamaEmbedder:
    def __init__(self) -> None:
        from langchain_ollama import OllamaEmbeddings

        self.model_name = settings.ollama_embed_model
        self.input_version = "nomic-heading-v2" if self.model_name.split(":")[0] == "nomic-embed-text" else "heading-v1"
        if "bge-small-zh-v1.5" in self.model_name:
            self.input_version = "bge-zh-heading-v1"
        self._embeddings = OllamaEmbeddings(
            model=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
            client_kwargs={"timeout": settings.ollama_timeout_seconds},
        )

    def embed_query(self, text: str) -> list[float]:
        prefix = "search_query: " if self.input_version == "nomic-heading-v2" else ""
        if self.input_version == "bge-zh-heading-v1":
            prefix = "为这个句子生成表示以用于检索相关文章："
        return self._embeddings.embed_query(prefix + text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefix = "search_document: " if self.input_version == "nomic-heading-v2" else ""
        return self._embeddings.embed_documents([prefix + text for text in texts])


def create_embedder():
    if settings.embedding_provider == "zhipu":
        from app.rag.cloud_embeddings import ZhipuEmbedder
        return ZhipuEmbedder()
    return OllamaEmbedder()


def retrieve_store_knowledge(question: str) -> dict:
    base = KnowledgeBase(settings.chroma_path)
    if base.has_vectors():
        try:
            hits = base.semantic_search(question, create_embedder())
            if hits:
                return {"mode": "chroma", "hits": hits}
        except Exception as exc:
            if settings.rag_require_vectors:
                raise RuntimeError("严格模式语义检索失败") from exc
            logger.warning("向量检索失败，退回关键词：%s", exc)
    if settings.rag_require_vectors:
        raise RuntimeError("严格模式要求已建立且可检索的向量索引")
    return {"mode": "keyword", "hits": keyword_search(question)}


def search_store_knowledge(question: str) -> str:
    return format_hits(retrieve_store_knowledge(question)["hits"])


def reindex_knowledge() -> dict:
    chunks = KnowledgeBase(settings.chroma_path).load_chunks()
    try:
        written = KnowledgeBase(settings.chroma_path).rebuild(chunks, create_embedder())
    except Exception as exc:
        if settings.rag_require_vectors:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail="真实 Embedding 索引构建失败") from exc
        logger.warning("知识库向量重建失败：%s", exc)
        return {
            "chunks": len(chunks),
            "mode": "keyword",
            "detail": f"向量模型不可用，问答仍按关键词检索原文。{exc}",
        }
    return {"chunks": written, "mode": "chroma", "detail": "已把知识文档写入 Chroma。"}
