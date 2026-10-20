from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Lock
import time
from uuid import uuid4

from filelock import FileLock

from app.core.config import settings
from app.core.credentials import embedding_api_key
from app.core.logging import logger
from app.rag.cloud_embeddings import EmbeddingQuotaError


_cooldowns = {}
_lock = Lock()


def candidates():
    models = list(dict.fromkeys([settings.cloud_embedding_model] + [name.strip() for name in settings.cloud_embedding_fallback_models.split(",") if name.strip()]))
    if len(models) > 5:
        raise ValueError("Embedding候选模型最多5个")
    if settings.embedding_provider not in {"qwen", "zhipu"}:
        raise ValueError("Embedding自动切换仅支持已配置的同供应商云端模型")
    return models


def scope(model):
    return (settings.embedding_provider, settings.cloud_embedding_base_url or settings.cloud_base_url,
            sha256(embedding_api_key().encode()).hexdigest(), model)


def cooling(model):
    with _lock:
        return _cooldowns.get(scope(model), 0) > time.monotonic()


def mark_quota(model):
    with _lock:
        _cooldowns[scope(model)] = time.monotonic() + settings.cloud_fallback_cooldown_seconds
    logger.warning("Embedding quota exhausted; model=%s; selecting configured next model", model)


def manifest_path():
    root = Path(settings.chroma_path)
    root.mkdir(parents=True, exist_ok=True)
    return root / ("knowledge-" + sha256(settings.chroma_collection.encode()).hexdigest()[:16] + ".json")


def base_for(model, embedder):
    from app.rag.knowledge import KnowledgeBase
    collection = settings.chroma_collection
    if model != settings.cloud_embedding_model:
        suffix = sha256((model + ":" + embedder.input_version).encode()).hexdigest()[:16]
        collection = collection[:480] + "_fallback_" + suffix
    return KnowledgeBase(settings.chroma_path, collection)


def rebuild(chunks):
    from app.rag.knowledge import create_embedder
    manifest = manifest_path()
    with FileLock(str(manifest) + ".lock", timeout=60):
        for model in candidates():
            if cooling(model):
                continue
            embedder = create_embedder(model)
            base = base_for(model, embedder)
            try:
                written = base.rebuild(chunks, embedder)
            except EmbeddingQuotaError:
                mark_quota(model)
                continue
            temporary = manifest.with_name(manifest.name + "." + uuid4().hex + ".tmp")
            try:
                temporary.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
                os.replace(temporary, manifest)
            finally:
                temporary.unlink(missing_ok=True)
            return {"chunks": written, "mode": "chroma", "embedding_model": model, "collection": base.collection,
                    "detail": "知识索引已更新，候选模型使用独立向量集合。"}
    raise EmbeddingQuotaError("所有Embedding候选模型额度耗尽或处于冷却期")


def retrieve(question):
    from app.rag.knowledge import KnowledgeBase, create_embedder
    manifest = manifest_path()
    with FileLock(str(manifest) + ".lock", timeout=60):
        primary = KnowledgeBase(settings.chroma_path)
        chunks = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else primary.export_chunks()
        if not chunks:
            raise RuntimeError("严格模式要求已建立且可检索的向量索引")
        for model in candidates():
            if cooling(model):
                continue
            embedder = create_embedder(model)
            base = base_for(model, embedder)
            try:
                base.rebuild(chunks, embedder)
                hits = base.semantic_search(question, embedder)
            except EmbeddingQuotaError:
                mark_quota(model)
                continue
            for hit in hits:
                hit["embedding_model"] = model
            return {"mode": "chroma", "hits": hits, "embedding_model": model, "collection": base.collection}
    raise EmbeddingQuotaError("所有Embedding候选模型额度耗尽或处于冷却期")
