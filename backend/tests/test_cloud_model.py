import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from app.agent.model import CloudChatModel
from app.core.config import settings


def test_cloud_tool_messages(monkeypatch):
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
