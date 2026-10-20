import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from app.agent.model import CloudChatModel
from app.core.config import settings


@pytest.fixture(autouse=True)
def isolated_quota_state(monkeypatch):
    from app.agent.model import _quota_cooldowns, cloud_http
    monkeypatch.setattr(cloud_http, "post", lambda *args, **kwargs: httpx.post(*args, **kwargs))
    _quota_cooldowns.clear()
    monkeypatch.setattr(settings, "cloud_fallback_models", "")
    yield
    _quota_cooldowns.clear()


def test_cloud_tool_messages(monkeypatch):
    monkeypatch.setattr(settings, "cloud_model", "qwen-plus-2025-04-28")
    monkeypatch.setattr(settings, "cloud_api_style", "qwen")
    monkeypatch.setattr(settings, "cloud_api_key", "test-secret")
    monkeypatch.setattr(settings, "cloud_base_url", "https://example.test/compatible-mode/v1")
    requests = []
    def post(url, **kwargs):
        requests.append(kwargs["json"])
        if len(requests) == 1:
            message = {"content": None, "tool_calls": [{"id": "call1", "type": "function", "function": {"name": "search_products", "arguments": '{"keyword":"杯"}'}}]}
        else:
            message = {"content": "查到了商品"}
        return httpx.Response(200, json={"choices": [{"message": message}]})
    monkeypatch.setattr(httpx, "post", post)
    model = CloudChatModel([{"type": "function", "function": {"name": "search_products"}}])
    first = model.invoke([HumanMessage(content="有没有杯子")])
    assert first.tool_calls[0]["args"] == {"keyword": "杯"}
    second = model.invoke([HumanMessage(content="有没有杯子"), first, ToolMessage(content="马克杯39元", tool_call_id="call1")])
    assert second.content == "查到了商品"
    assert requests[1]["messages"][-1]["tool_call_id"] == "call1"
    assert requests[0]["model"] == "qwen-plus-2025-04-28"
    assert requests[0]["enable_thinking"] is False


def test_cloud_failure_does_not_leak_key(monkeypatch):
    monkeypatch.setattr(settings, "cloud_api_key", "secret-never-log")
    monkeypatch.setattr(settings, "cloud_base_url", "https://example.test/v1")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(403, text="secret-never-log"))
    with pytest.raises(RuntimeError, match="HTTP 403") as error:
        CloudChatModel().invoke([HumanMessage(content="你好")])
    assert "secret-never-log" not in str(error.value)


def test_cloud_rate_limit_retries(monkeypatch):
    monkeypatch.setattr(settings, "cloud_api_key", "test-secret")
    monkeypatch.setattr(settings, "cloud_base_url", "https://example.test/v1")
    responses = iter([httpx.Response(429), httpx.Response(200, json={"choices": [{"message": {"content": "成功"}}]})])
    monkeypatch.setattr(httpx, "post", lambda *a, **k: next(responses))
    sleeps = []
    monkeypatch.setattr("app.agent.model.time.sleep", sleeps.append)
    assert CloudChatModel().invoke([HumanMessage(content="你好")]).content == "成功"
    assert sleeps == [2]


def test_zhipu_key_file_and_tool_protocol(monkeypatch, tmp_path):
    key_file = tmp_path / "key.txt"
    key_file.write_text("\ufefftest-file-key\n", encoding="utf-8")
    monkeypatch.setattr(settings, "cloud_api_key", "")
    monkeypatch.setattr(settings, "cloud_api_key_file", str(key_file))
    monkeypatch.setattr(settings, "cloud_api_style", "zhipu")
    monkeypatch.setattr(settings, "cloud_model", "glm-4.7-flash")
    monkeypatch.setattr(settings, "cloud_base_url", "https://open.bigmodel.cn/api/paas/v4")
    def post(url, **kwargs):
        assert url == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-file-key"
        assert kwargs["json"]["thinking"] == {"type": "disabled"}
        assert "enable_thinking" not in kwargs["json"]
        assert kwargs["json"]["tools"][0]["function"]["name"] == "search_products"
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "native1", "function": {"name": "search_products", "arguments": '{"keyword":"杯"}'}}]}}]})
    monkeypatch.setattr(httpx, "post", post)
    model = CloudChatModel().bind_tools([{"type": "function", "function": {"name": "search_products", "parameters": {"type": "object", "properties": {}}}}])
    assert model.invoke([HumanMessage(content="找杯子")]).tool_calls[0]["args"] == {"keyword": "杯"}


@pytest.mark.parametrize("content", ["", "test-key\nsecond-key", "test key"])
def test_key_file_invalid_content_never_sent(monkeypatch, tmp_path, content):
    key_file = tmp_path / "key.txt"
    key_file.write_text(content, encoding="utf-8")
    monkeypatch.setattr(settings, "cloud_api_key", "")
    monkeypatch.setattr(settings, "cloud_api_key_file", str(key_file))
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: pytest.fail("invalid credential sent"))
    with pytest.raises(RuntimeError, match="格式无效"):
        CloudChatModel().invoke([HumanMessage(content="你好")])


def test_key_file_read_error_redacts_path(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cloud_api_key", "")
    monkeypatch.setattr(settings, "cloud_api_key_file", str(tmp_path / "private-key.txt"))
    with pytest.raises(RuntimeError, match="无法读取") as error:
        CloudChatModel().invoke([HumanMessage(content="你好")])
    assert "private-key" not in str(error.value)


@pytest.mark.parametrize("model_name", ["glm-5.3-flash", "glm-5.3-flashx"])
def test_glm53_required_thinking_and_tool_reasoning_roundtrip(monkeypatch, model_name):
    monkeypatch.setattr(settings, "cloud_api_key", "test-only")
    monkeypatch.setattr(settings, "cloud_base_url", "https://example.test/v4")
    monkeypatch.setattr(settings, "cloud_api_style", "zhipu")
    monkeypatch.setattr(settings, "cloud_model", model_name)
    monkeypatch.setattr(settings, "cloud_max_tokens", 4096)
    requests = []
    def post(url, **kwargs):
        body = kwargs["json"]
        requests.append(body)
        assert body["thinking"] == {"type": "enabled", "clear_thinking": False}
        assert body["reasoning_effort"] == "low" and body["max_tokens"] == 4096
        assert body["temperature"] == 1 and "enable_thinking" not in body
        if len(requests) == 1:
            message = {"reasoning_content": "synthetic reasoning", "tool_calls": [{"id": "call1", "function": {"name": "search_products", "arguments": '{}'}}]}
        else:
            assert body["messages"][-2]["reasoning_content"] == "synthetic reasoning"
            message = {"content": "已查询"}
        return httpx.Response(200, json={"choices": [{"message": message}]})
    monkeypatch.setattr(httpx, "post", post)
    model = CloudChatModel()
    first = model.invoke([HumanMessage(content="查商品")])
    result = model.invoke([HumanMessage(content="查商品"), first, ToolMessage(content="测试商品", tool_call_id="call1")])
    assert result.content == "已查询"


def configure_chain(monkeypatch):
    monkeypatch.setattr(settings, "cloud_api_key", "test-only")
    monkeypatch.setattr(settings, "cloud_base_url", "https://example.test/v4")
    monkeypatch.setattr(settings, "cloud_api_style", "zhipu")
    monkeypatch.setattr(settings, "cloud_model", "glm-5.3-flash")
    monkeypatch.setattr(settings, "cloud_fallback_models", "glm-5.3-flashx,glm-5.3,glm-4.7-flash")


@pytest.mark.parametrize("code", [1113, "1113", "1308", "1310"])
def test_quota_switch_preserves_tools_and_skips_cooldown(monkeypatch, code):
    configure_chain(monkeypatch)
    requests = []
    def post(url, **kwargs):
        body = kwargs["json"]
        requests.append(body)
        if body["model"] == "glm-5.3-flash":
            return httpx.Response(429, json={"error": {"code": code, "message": "secret-never-log"}})
        assert body["tools"] and body["thinking"]["type"] == "enabled"
        return httpx.Response(200, json={"choices": [{"message": {"content": "成功"}}]})
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr("app.agent.model.time.sleep", lambda duration: pytest.fail("quota must not retry same model"))
    model = CloudChatModel([{"type": "function", "function": {"name": "search_products"}}])
    assert model.invoke([HumanMessage(content="查商品")]).response_metadata["model"] == "glm-5.3-flashx"
    CloudChatModel(model.tools).invoke([HumanMessage(content="继续")])
    assert [body["model"] for body in requests] == ["glm-5.3-flash", "glm-5.3-flashx", "glm-5.3-flashx"]


def test_all_quota_exhausted_is_bounded_and_redacted(monkeypatch):
    configure_chain(monkeypatch)
    seen = []
    def post(url, **kwargs):
        seen.append(kwargs["json"])
        return httpx.Response(429, json={"error": {"code": "1113", "message": "secret-never-log"}})
    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(RuntimeError, match="所有候选模型") as error:
        CloudChatModel().invoke([HumanMessage(content="你好")])
    assert len(seen) == 4 and seen[-1]["thinking"] == {"type": "disabled"}
    assert "secret-never-log" not in str(error.value)


@pytest.mark.parametrize("status,code", [(401, "1000"), (400, "1301"), (400, "1210"), (429, "1302"), (503, None)])
def test_non_quota_errors_do_not_switch_models(monkeypatch, status, code):
    configure_chain(monkeypatch)
    seen = []
    def post(url, **kwargs):
        seen.append(kwargs["json"]["model"])
        return httpx.Response(status, json={"error": {"code": code}})
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr("app.agent.model.time.sleep", lambda duration: None)
    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        CloudChatModel().invoke([HumanMessage(content="你好")])
    assert set(seen) == {"glm-5.3-flash"}


def test_quota_cooldown_expires(monkeypatch):
    configure_chain(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr("app.agent.model.time.monotonic", lambda: clock[0])
    seen = []
    def post(url, **kwargs):
        name = kwargs["json"]["model"]
        seen.append(name)
        if name == "glm-5.3-flash" and clock[0] == 100:
            return httpx.Response(429, json={"error": {"code": "1113"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "成功"}}]})
    monkeypatch.setattr(httpx, "post", post)
    model = CloudChatModel()
    model.invoke([HumanMessage(content="你好")])
    clock[0] = 401
    assert model.invoke([HumanMessage(content="你好")]).response_metadata["model"] == "glm-5.3-flash"
