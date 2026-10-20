import httpx
import pytest

from app.core.config import settings
from app.rag.cloud_embeddings import ZhipuEmbedder


@pytest.fixture(autouse=True)
def cloud_configuration(monkeypatch):
    monkeypatch.setattr(settings, "cloud_api_style", "zhipu")
    monkeypatch.setattr(settings, "cloud_base_url", "https://example.test/v4")
    monkeypatch.setattr(settings, "cloud_api_key", "test-only")
    monkeypatch.setattr(settings, "cloud_embedding_dimensions", 256)
    monkeypatch.setattr(settings, "cloud_embedding_model", "embedding-3")


def test_batching_sorting_and_embedding_protocol(monkeypatch):
    batches = []
    def post(url, **kwargs):
        body = kwargs["json"]
        assert url == "https://example.test/v4/embeddings"
        assert body["model"] == "embedding-3" and body["dimensions"] == 256
        batches.append(body["input"])
        return httpx.Response(200, json={"data": [{"index": index, "embedding": [index + 1] + [0] * 255} for index in reversed(range(len(body["input"])))]})
    monkeypatch.setattr(httpx, "post", post)
    model = ZhipuEmbedder()
    vectors = model.embed_documents(["测试" + str(index) for index in range(65)])
    assert [len(batch) for batch in batches] == [64, 1]
    assert len(vectors) == 65 and vectors[0][0] == 1 and vectors[63][0] == 64
    assert "256" in model.input_version
    assert model.embed_query("查询")[0] == 1


@pytest.mark.parametrize("data", [[], [{"index": 1, "embedding": [1] * 256}], [{"index": 0, "embedding": [1]}],
                                  [{"index": 0, "embedding": [0] * 256}], [{"index": 0, "embedding": [True] * 256}],
                                  [{"index": 0, "embedding": [float("nan")] * 256}]])
def test_invalid_vectors_are_rejected(monkeypatch, data):
    class Response:
        status_code = 200
        is_success = True
        def json(self):
            return {"data": data}
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match="Embedding返回"):
        ZhipuEmbedder().embed_query("问题")


def test_embedding_failures_are_bounded_and_redacted(monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(503, text="secret-never-log")
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr("app.rag.cloud_embeddings.time.sleep", lambda duration: None)
    with pytest.raises(RuntimeError, match="HTTP 503") as error:
        ZhipuEmbedder().embed_query("问题")
    assert len(calls) == 3 and "secret-never-log" not in str(error.value)


def test_cloud_dimension_change_rejects_old_collection(tmp_path, monkeypatch):
    from app.rag.knowledge import KnowledgeBase
    base = KnowledgeBase(tmp_path, "cloud_dimension_test")
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1] * 256}]}))
    base.rebuild([{"id": "test", "source": "test.md", "heading_path": "标题", "content": "测试"}], ZhipuEmbedder())
    monkeypatch.setattr(settings, "cloud_embedding_dimensions", 512)
    with pytest.raises(ValueError, match="输入格式"):
        base.semantic_search("问题", ZhipuEmbedder())


def test_qwen_embedding_uses_compatible_endpoint_and_ten_item_batches(monkeypatch):
    from app.rag.cloud_embeddings import QwenEmbedder
    from app.rag.knowledge import create_embedder
    monkeypatch.setattr(settings, "cloud_api_style", "qwen")
    monkeypatch.setattr(settings, "embedding_provider", "qwen")
    monkeypatch.setattr(settings, "cloud_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setattr(settings, "cloud_embedding_model", "text-embedding-v4")
    sizes = []
    def post(url, **kwargs):
        assert url.endswith("/compatible-mode/v1/embeddings")
        body = kwargs["json"]
        assert body["model"] == "text-embedding-v4" and body["dimensions"] == 256
        sizes.append(len(body["input"]))
        return httpx.Response(200, json={"data": [{"index": index, "embedding": [1.0] + [0.0] * 255} for index in range(len(body["input"]))]})
    monkeypatch.setattr(httpx, "post", post)
    embedder = create_embedder()
    assert isinstance(embedder, QwenEmbedder)
    assert len(embedder.embed_documents(["政策"] * 21)) == 21
    assert sizes == [10, 10, 1]
    assert embedder.input_version == "qwen-heading-v1-d256"


def test_embedding_quota_error_does_not_retry_chargeable_request(monkeypatch):
    calls = []
    def exhausted(*args, **kwargs):
        calls.append(1)
        return httpx.Response(429, json={"error": {"code": "1113", "message": "not-for-logs"}})
    monkeypatch.setattr(httpx, "post", exhausted)
    with pytest.raises(RuntimeError, match="1113"):
        ZhipuEmbedder().embed_query("政策")
    assert len(calls) == 1


def test_embedding_uses_separate_provider_and_never_chat_key(monkeypatch, tmp_path):
    key_file = tmp_path / "embedding-key.txt"
    key_file.write_text("embedding-test-only", encoding="utf-8")
    monkeypatch.setattr(settings, "cloud_api_style", "deepseek")
    monkeypatch.setattr(settings, "cloud_api_key", "chat-test-only")
    monkeypatch.setattr(settings, "cloud_base_url", "https://api.deepseek.com")
    monkeypatch.setattr(settings, "cloud_embedding_base_url", "https://example.test/vectors")
    monkeypatch.setattr(settings, "cloud_embedding_api_key_file", str(key_file))
    def post(url, **kwargs):
        assert url == "https://example.test/vectors/embeddings"
        assert kwargs["headers"]["Authorization"] == "Bearer embedding-test-only"
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0] * 256}]})
    monkeypatch.setattr(httpx, "post", post)
    assert len(ZhipuEmbedder().embed_query("政策")) == 256
    monkeypatch.setattr(settings, "cloud_embedding_api_key_file", "")
    with pytest.raises(RuntimeError, match="独立密钥"):
        ZhipuEmbedder().embed_query("政策")
