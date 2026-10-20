import httpx
import pytest

from app.core.config import settings
from app.rag import routing
from app.rag.knowledge import retrieve_store_knowledge, KnowledgeBase


@pytest.fixture()
def route(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "chroma_path", str(tmp_path))
    monkeypatch.setattr(settings, "chroma_collection", "quota-routing-test")
    monkeypatch.setattr(settings, "embedding_provider", "qwen")
    monkeypatch.setattr(settings, "cloud_embedding_model", "primary-test")
    monkeypatch.setattr(settings, "cloud_embedding_fallback_models", "fallback-test")
    monkeypatch.setattr(settings, "cloud_embedding_dimensions", 256)
    monkeypatch.setattr(settings, "cloud_embedding_base_url", "https://example.test/v1")
    monkeypatch.setattr(settings, "cloud_embedding_api_key", "embedding-test-only")
    routing._cooldowns.clear()
    yield tmp_path
    routing._cooldowns.clear()


def test_embedding_quota_falls_back_without_mixing_vector_spaces(route, monkeypatch):
    calls = []
    exhausted = set()
    def transport(url, **kwargs):
        body = kwargs["json"]
        calls.append(body["model"])
        if body["model"] in exhausted:
            return httpx.Response(403, json={"error": {"code": "AllocationQuota.FreeTierOnly"}})
        vector = [1.0, 0.0] if body["model"] == "primary-test" else [0.0, 1.0]
        return httpx.Response(200, json={"data": [{"index": index, "embedding": vector + [0.0] * 254} for index in range(len(body["input"]))]})
    monkeypatch.setattr(httpx, "post", transport)
    chunk = {"id": "policy", "source": "rules.md", "content": "延保37天"}
    first = routing.rebuild([chunk])
    exhausted.add("primary-test")
    second = retrieve_store_knowledge("延保")
    assert second["embedding_model"] == "fallback-test"
    assert second["collection"] != first["collection"]
    assert second["hits"][0]["content"] == "延保37天"
    before = calls.count("primary-test")
    routing.rebuild([{**chunk, "content": "延保43天"}])
    assert retrieve_store_knowledge("延保")["hits"][0]["content"] == "延保43天"
    assert calls.count("primary-test") == before
    exhausted.clear();routing._cooldowns.clear()
    assert retrieve_store_knowledge("延保")["hits"][0]["content"] == "延保43天"
    assert KnowledgeBase(route).export_chunks()[0]["content"] == "延保43天"


def test_embedding_auth_error_does_not_switch_or_use_chat_key(route, monkeypatch):
    calls = []
    def transport(url, **kwargs):
        calls.append(kwargs["json"]["model"])
        assert kwargs["headers"]["Authorization"] == "Bearer embedding-test-only"
        return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})
    monkeypatch.setattr(httpx, "post", transport)
    with pytest.raises(RuntimeError, match="401"):
        routing.rebuild([{"id": "policy", "source": "rules.md", "content": "政策"}])
    assert calls == ["primary-test"]


def test_all_embedding_quotas_exhausted_is_bounded(route, monkeypatch):
    calls = []
    def transport(url, **kwargs):
        calls.append(kwargs["json"]["model"])
        return httpx.Response(403, json={"error": {"code": "AllocationQuota.FreeTierOnly"}})
    monkeypatch.setattr(httpx, "post", transport)
    with pytest.raises(RuntimeError, match="所有Embedding"):
        routing.rebuild([{"id": "policy", "source": "rules.md", "content": "政策"}])
    assert calls == ["primary-test", "fallback-test"]
