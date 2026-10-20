import json

import pytest

from app.agent.intent import classify


def login(client, username="alice"):
    token = client.post("/api/v1/auth/login", json={"username": username, "password": username + "123"}).json()["access_token"]
    return {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("message", ["我要睡觉用的东西", "我需要卧室用的商品", "帮我找记笔记用的东西"])
def test_purpose_recommendation_routing(message):
    assert classify(message) == "recommend"


@pytest.mark.parametrize("message,intent", [("我要睡觉用的东西怎么清洗", "policy"), ("我要查询订单", "order"), ("抱枕有货吗", "inventory")])
def test_specific_intent_keeps_priority(message, intent):
    assert classify(message) == intent


@pytest.mark.parametrize("username,path", [("alice", "/api/v1/c/shops/nanzhi/chat/stream"), ("merchant", "/api/v1/b/chat/stream")])
def test_stream_result_and_authentication(client, username, path):
    assert client.post(path, json={"message": "查询商品"}).status_code == 401
    response = client.post(path, headers=login(client, username), json={"message": "抱枕有货吗"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["stage"] == "accepted"
    assert events[-1]["type"] == "result"
    assert events[-1]["data"]["mode"] == "direct"
    assert events[-1]["data"]["tools"]
    assert any(event.get("stage") == "context" for event in events)


def test_stream_role_isolation(client):
    assert client.post("/api/v1/b/chat/stream", headers=login(client), json={"message": "经营概览"}).status_code == 403
    assert client.post("/api/v1/c/shops/nanzhi/chat/stream", headers=login(client, "merchant"), json={"message": "订单"}).status_code == 403


def test_stream_internal_error_is_redacted(client, monkeypatch):
    from app.agent.assistant import assistant
    def fail(**kwargs):
        raise RuntimeError("private-key-and-database-password")
    monkeypatch.setattr(assistant, "chat", fail)
    response = client.post("/api/v1/c/shops/nanzhi/chat/stream", headers=login(client), json={"message": "查询商品"})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "error"
    assert "private-key" not in response.text


def test_stream_real_loop_progress_has_model_and_guarded_tool_stages(client, monkeypatch):
    import importlib
    from langchain_core.messages import AIMessage
    from app.core.config import settings
    module = importlib.import_module("app.agent.assistant")
    # This test targets the model/tool loop, independently of the direct fact route.
    monkeypatch.setattr("app.agent.product_preview.product_quick_reply", lambda message: None)
    class Model:
        def __init__(self):
            self.calls = 0
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content="", tool_calls=[{"name": "search_products", "args": {"keyword": "抱枕"}, "id": "call1"}])
            return AIMessage(content="已查询本店抱枕库存")
    monkeypatch.setattr(settings, "agent_mode", "auto")
    monkeypatch.setattr(module, "create_chat_model", Model)
    response = client.post("/api/v1/c/shops/nanzhi/chat/stream", headers=login(client), json={"message": "抱枕有货吗"})
    events = [json.loads(line) for line in response.text.splitlines()]
    stages = [event.get("stage") for event in events]
    assert stages.count("model") == 2
    assert stages.count("model_done") == 2
    assert stages.index("tool") < stages.index("tool_done")
    assert events[-1]["data"]["mode"] == "llm"
    assert events[-1]["data"]["tools"][0]["tool"] == "search_products"


def test_stream_business_error_remains_error_not_fallback(client, monkeypatch):
    from fastapi import HTTPException
    from app.agent.assistant import assistant
    def fail(**kwargs):
        raise HTTPException(429, "请求过于频繁")
    monkeypatch.setattr(assistant, "chat", fail)
    response = client.post("/api/v1/c/shops/nanzhi/chat/stream", headers=login(client), json={"message": "查询商品"})
    event = json.loads(response.text.splitlines()[-1])
    assert event == {**event, "type": "error", "status": 429, "detail": "请求过于频繁"}


def test_stream_rejects_other_buyers_order(client):
    response = client.post("/api/v1/c/shops/nanzhi/chat/stream", headers=login(client), json={"message": "查询订单 PS202601200001"})
    result = json.loads(response.text.splitlines()[-1])["data"]
    assert "没有找到这个订单" in result["answer"]
    assert "益阳" not in response.text
