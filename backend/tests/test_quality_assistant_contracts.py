import pytest
from pydantic import ValidationError

from app.quality.catalog import ASSISTANT_CASES, case_by_id
from app.quality.service import PlanIn
from app.quality.sandbox import ModelBudget


def test_all_assistant_ids_have_explicit_adapters_and_modes():
    assert ASSISTANT_CASES == {f"A{index:02}" for index in range(1, 41)}
    assert case_by_id("A15")["modes"] == ["live"]
    for case_id in ["A05", "A10", "A15", "A20", "A35", "A40"]:
        with pytest.raises(ValidationError, match="执行模式"):
            PlanIn(goal="验证真实模型能力", kind="assistant", case_ids=[case_id], mode="rules")
        assert PlanIn(goal="验证真实模型能力", kind="assistant", case_ids=[case_id], mode="live")


def test_embedding_budget_counts_actual_usage_and_restores(monkeypatch):
    import httpx
    from app.core.config import settings
    monkeypatch.setattr(settings, "model_provider", "cloud")
    def transport(url, **kwargs):
        return httpx.Response(200, json={"usage": {"total_tokens": 19}, "data": []})
    monkeypatch.setattr(httpx, "post", transport)
    budget = ModelBudget(1, 5000)
    restore = budget.install()
    try:
        httpx.post("https://example.test/embeddings", json={"model": "embedding-test", "input": ["政策"]})
        assert budget.calls == 1 and budget.tokens == 19
        assert budget.models[0]["kind"] == "embedding"
        with pytest.raises(RuntimeError, match="预算"):
            httpx.post("https://example.test/embeddings", json={"input": ["政策"]})
    finally:
        restore()
    assert httpx.post is transport


def test_real_chroma_versions_update_and_no_hit(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.rag.knowledge import KnowledgeBase
    class FixedVectors:
        model_name = "test-contract-only"
        def embed_documents(self, texts):
            return [[1.0, 0.0] for text in texts]
        def embed_query(self, question):
            return [1.0, 0.0] if question == "政策" else [-1.0, 0.0]
    base = KnowledgeBase(tmp_path)
    embedder = FixedVectors()
    monkeypatch.setattr(settings, "rag_max_distance", 0.65)
    chunk = {"id": "policy", "content": "延保37天", "source": "test.md"}
    base.rebuild([chunk], embedder)
    old = base.semantic_search("政策", embedder)[0]
    assert old["chunk_id"] == "policy" and len(old["version"]) == 64
    base.rebuild([{**chunk, "content": "延保43天"}], embedder)
    new = base.semantic_search("政策", embedder)[0]
    assert new["version"] != old["version"] and new["content"] == "延保43天"
    assert base.semantic_search("无关", embedder) == []


def test_incremental_reindex_only_embeds_changed_chunks(tmp_path):
    from app.rag.knowledge import KnowledgeBase
    calls = []
    class FixedVectors:
        model_name = "test-incremental-only"
        def embed_documents(self, texts):
            calls.append(texts)
            return [[1.0, 0.0] for text in texts]
    base = KnowledgeBase(tmp_path)
    embedder = FixedVectors()
    chunks = [{"id": "first", "source": "test.md", "content": "首次说明"}, {"id": "second", "source": "test.md", "content": "第二条说明"}]
    assert base.rebuild(chunks, embedder) == 2 and len(calls) == 1
    assert base.rebuild(chunks, embedder) == 2 and len(calls) == 1
    base.rebuild([chunks[0], {**chunks[1], "content": "更新说明"}], embedder)
    assert len(calls) == 2 and len(calls[-1]) == 1 and "更新说明" in calls[-1][0]
    base.rebuild([chunks[0]], embedder)
    assert len(calls) == 2
    assert base.rebuild([], embedder) == 0 and not base.has_vectors()
