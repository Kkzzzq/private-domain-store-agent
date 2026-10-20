import httpx
import pytest
import redis
from fastapi import HTTPException

from app.core.config import settings
from app.db.redis_client import MemoryRedis, RedisClient
from app.services.session import compact_messages
from test_bc_link import login


def test_strict_readiness_rejects_sqlite_and_memory(client, monkeypatch):
    monkeypatch.setattr(settings, "strict_dependencies", True)
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": False, "redis": False}


def test_strict_redis_connection_does_not_fallback(monkeypatch):
    monkeypatch.setattr(settings, "strict_dependencies", True)
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    with pytest.raises(RuntimeError, match="Redis 不可用"):
        RedisClient().connect()


def test_runtime_redis_failure_modes(monkeypatch):
    cache = RedisClient()
    cache._client = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=.2)
    monkeypatch.setattr(settings, "strict_dependencies", True)
    with pytest.raises(HTTPException) as error:
        cache.get_json("contract")
    assert error.value.status_code == 503 and not cache.using_memory
    monkeypatch.setattr(settings, "strict_dependencies", False)
    cache.set_json("contract", {"value": 1})
    assert isinstance(cache._client, MemoryRedis)
    assert cache.get_json("contract") == {"value": 1}


def test_real_unreachable_model_returns_503(client, monkeypatch):
    buyer = login(client, "alice")
    monkeypatch.setattr(settings, "agent_mode", "auto")
    monkeypatch.setattr(settings, "agent_require_llm", True)
    monkeypatch.setattr(settings, "model_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:1")
    monkeypatch.setattr(settings, "ollama_timeout_seconds", 1)
    response = client.post("/api/v1/c/shops/nanzhi/chat", headers=buyer, json={"message": "搜索抱枕商品"})
    assert response.status_code == 503
    assert "fallback" not in response.text


def test_strict_rag_missing_index_does_not_keyword_fallback(tmp_path, monkeypatch):
    from app.rag.knowledge import retrieve_store_knowledge
    monkeypatch.setattr(settings, "chroma_path", str(tmp_path))
    monkeypatch.setattr(settings, "rag_require_vectors", True)
    with pytest.raises(RuntimeError, match="向量索引"):
        retrieve_store_knowledge("退货政策")


def test_real_unreachable_embedding_reindex_returns_503(client, monkeypatch):
    merchant = login(client, "merchant")
    monkeypatch.setattr(settings, "rag_require_vectors", True)
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:1")
    monkeypatch.setattr(settings, "ollama_timeout_seconds", 1)
    response = client.post("/api/v1/b/knowledge/reindex", headers=merchant)
    assert response.status_code == 503
    assert "Embedding" in response.json()["detail"]


def test_cloud_summary_uses_messages_and_reports_model_mode(monkeypatch):
    from app.agent.model import CloudChatModel, cloud_http
    monkeypatch.setattr(settings, "cloud_api_key", "test-only")
    monkeypatch.setattr(settings, "cloud_base_url", "https://example.test/v1")
    captured = []
    def post(url, **kwargs):
        captured.append(kwargs["json"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "用户关注订单PS202601200001"}}]})
    monkeypatch.setattr(cloud_http, "post", post)
    state, notice = compact_messages({"messages": [{"role": "user", "content": "PS202601200001 " + "查询" * 500}]}, 800, CloudChatModel())
    assert notice and state["summary_mode"] == "llm"
    assert captured[0]["messages"][0]["role"] == "user"
    assert "PS202601200001" in state["summary"]


def test_embedding_model_mismatch_is_rejected(tmp_path):
    from app.rag.knowledge import KnowledgeBase
    class Embeddings:
        model_name = "first-model"
        def embed_documents(self, texts):
            return [[1.0, 0.0] for text in texts]
        def embed_query(self, text):
            return [1.0, 0.0]
    base = KnowledgeBase(tmp_path)
    embedder = Embeddings()
    base.rebuild([{"id": "first", "content": "售后", "source": "policy.md"}], embedder)
    embedder.model_name = "different-model"
    with pytest.raises(ValueError, match="不一致"):
        base.semantic_search("售后", embedder)
    with pytest.raises(ValueError, match="模型已改变"):
        base.rebuild([{"id": "second", "content": "退货", "source": "policy.md"}], embedder)
    assert base.has_vectors()


def test_strict_tool_loop_requires_final_model_answer(client, monkeypatch):
    from langchain_core.messages import AIMessage
    from app.agent.assistant import ModelOutputError, run_tool_loop
    from app.agent.context import Actor, set_actor, reset_actor
    from app.db.session import SessionLocal
    from app.models.tables import User
    from sqlalchemy import select
    class LoopingModel:
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            return AIMessage(content="", tool_calls=[{"name": "query_orders", "args": {}, "id": "loop"}])
    monkeypatch.setattr(settings, "agent_require_llm", True)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        token = set_actor(db, Actor(user.id, user.role, user.username, 1))
        try:
            with pytest.raises(ModelOutputError, match="步骤上限"):
                run_tool_loop([], "", "我的订单", llm=LoopingModel(), max_steps=1)
        finally:
            reset_actor(token)


def test_chat_returns_structured_retrieval_sources(client, monkeypatch):
    monkeypatch.setattr("app.agent.tools.retrieve_store_knowledge", lambda question: {
        "mode": "chroma", "hits": [{"source": "after_sales.md", "heading_path": "售后", "content": "定制品不支持无理由退货", "distance": .2}]})
    buyer = login(client, "alice")
    response = client.post("/api/v1/c/shops/nanzhi/chat", headers=buyer, json={"message": "定制品能退货吗"})
    assert response.status_code == 200
    assert response.json()["retrieval_mode"] == "chroma"
    assert response.json()["sources"][0]["source"] == "after_sales.md"


def test_model_download_segment_resume(tmp_path, monkeypatch):
    import io
    from scripts.pull_ollama_model import download_segment
    segment = tmp_path / "model.segment0"
    segment.write_bytes(b"abc")
    requests = []
    class Response(io.BytesIO):
        status = 206
        headers = {"Content-Range": "bytes 103-109/200"}
    class Opener:
        def open(self, request, timeout):
            requests.append(request.get_header("Range"))
            return Response(b"defghij")
    download_segment(Opener(), "https://registry.ollama.ai/model", segment, 100, 10, "example")
    assert requests == ["bytes=103-109"]
    assert segment.read_bytes() == b"abcdefghij"


@pytest.mark.parametrize("model,query_prefix,document_prefix", [
    ("nomic-embed-text", "search_query: ", "search_document: "),
    ("quentinz/bge-small-zh-v1.5", "为这个句子生成表示以用于检索相关文章：", ""),
])
def test_retrieval_task_prefixes(monkeypatch, model, query_prefix, document_prefix):
    from app.rag.knowledge import OllamaEmbedder
    queries = []
    documents = []
    class Backend:
        def __init__(self, **kwargs):
            pass
        def embed_query(self, value):
            queries.append(value)
            return [1.0, 0.0]
        def embed_documents(self, values):
            documents.extend(values)
            return [[1.0, 0.0] for value in values]
    monkeypatch.setattr(settings, "ollama_embed_model", model)
    monkeypatch.setattr("langchain_ollama.OllamaEmbeddings", Backend)
    embedder = OllamaEmbedder()
    embedder.embed_query("退货时限")
    embedder.embed_documents(["七天退货"])
    assert queries == [query_prefix + "退货时限"]
    assert documents == [document_prefix + "七天退货"]


@pytest.mark.parametrize("args", ["{broken", "[]", "123", [1, 2]])
def test_malformed_model_tool_args_cannot_become_empty_order_query(client, args):
    from app.agent.context import Actor, set_actor, reset_actor
    from app.agent.guard import execute_tool
    from app.db.session import SessionLocal
    from app.models.tables import User
    from sqlalchemy import select
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        token = set_actor(db, Actor(user.id, user.role, user.username, 1))
        try:
            assert "参数缺失或无效" in execute_tool("query_orders", args)
        finally:
            reset_actor(token)


@pytest.mark.parametrize("recovers", [True, False])
def test_ungrounded_business_reply_has_one_model_correction(client, monkeypatch, recovers):
    from langchain_core.messages import AIMessage
    from app.agent.assistant import ModelOutputError, run_tool_loop
    from app.agent.context import Actor, set_actor, reset_actor
    from app.agent.tools import langchain_tools
    from app.db.session import SessionLocal
    from app.models.tables import User
    from sqlalchemy import select
    class Model:
        calls = 0
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            self.calls += 1
            if recovers and self.calls == 2:
                return AIMessage(content="", tool_calls=[{"name": "query_orders", "args": {}, "id": "corrected"}])
            return AIMessage(content="已查询。" if self.calls > 2 else "直接回答但没有工具依据")
    monkeypatch.setattr(settings, "agent_require_llm", True)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        actor = Actor(user.id, user.role, user.username, 1)
        token = set_actor(db, actor)
        model = Model()
        try:
            assert [tool.name for tool in langchain_tools("recommend")] == ["get_store_catalog"]
            if recovers:
                answer, traces = run_tool_loop([], "", "我的订单", llm=model)
                assert answer == "已查询。" and traces[0]["tool"] == "query_orders"
                assert model.calls == 3
            else:
                with pytest.raises(ModelOutputError, match="纠正后"):
                    run_tool_loop([], "", "我的订单", llm=model)
                assert model.calls == 2
            assert actor.model_retries == 1
        finally:
            reset_actor(token)
