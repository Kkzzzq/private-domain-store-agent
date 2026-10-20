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
