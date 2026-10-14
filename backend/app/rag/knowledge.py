from pathlib import Path

from app.core.config import settings
from app.core.logging import logger
from app.rag.cleaner import structured_chunks


class KnowledgeBase:
    def __init__(self, persist_dir: str | Path, collection: str = "store_knowledge") -> None:
        self.persist_dir = Path(persist_dir)
        self.collection = collection

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
        vectors = embedder.embed_documents([item["content"] for item in chunks]) if chunks else []
        collection = client.get_or_create_collection(
            self.collection, metadata={"hnsw:space": "cosine"}
        )
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
        total = collection.count()
        if total == 0:
            return []
        vector = embedder.embed_query(question)
        result = collection.query(query_embeddings=[vector], n_results=min(k, total))
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        hits = []
        for index, document in enumerate(documents):
            meta = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
            hits.append({"content": document, "source": meta.get("source", "chroma"), "heading_path": meta.get("heading_path", "正文")})
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

        self._embeddings = OllamaEmbeddings(
            model=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
        )

    def embed_query(self, text: str) -> list[float]:
        return self._embeddings.embed_query(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embeddings.embed_documents(texts)


def search_store_knowledge(question: str) -> str:
    base = KnowledgeBase(settings.chroma_path)
    if base.has_vectors():
        try:
            hits = base.semantic_search(question, OllamaEmbedder())
            if hits:
                return format_hits(hits)
        except Exception as exc:
            logger.warning("向量检索失败，退回关键词：%s", exc)
    return format_hits(keyword_search(question))


def reindex_knowledge() -> dict:
    chunks = KnowledgeBase(settings.chroma_path).load_chunks()
    try:
        written = KnowledgeBase(settings.chroma_path).rebuild(chunks, OllamaEmbedder())
    except Exception as exc:
        logger.warning("知识库向量重建失败：%s", exc)
        return {
            "chunks": len(chunks),
            "mode": "keyword",
            "detail": f"向量模型不可用，问答仍按关键词检索原文。{exc}",
        }
    return {"chunks": written, "mode": "chroma", "detail": "已把知识文档写入 Chroma。"}
