import json
import time

import httpx

from app.core.config import settings


class CloudChatModel:
    """Business-space API adapter; credentials stay in backend configuration."""

    def __init__(self, tools=None):
        self.tools = tools or []

    def bind_tools(self, tools):
        from langchain_core.utils.function_calling import convert_to_openai_tool
        return CloudChatModel([convert_to_openai_tool(tool) for tool in tools])

    def invoke(self, messages):
        from langchain_core.messages import AIMessage, convert_to_openai_messages
        if not settings.cloud_api_key or not settings.cloud_base_url:
            raise RuntimeError("云端模型未配置")
        body = {
            "model": settings.cloud_model,
            "messages": convert_to_openai_messages(messages),
            "temperature": 0,
            "max_tokens": 800,
            "enable_thinking": False,
        }
        if self.tools:
            body["tools"] = self.tools
        for attempt in range(4):
            response = httpx.post(
                settings.cloud_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + settings.cloud_api_key},
                json=body, timeout=45,
            )
            if response.status_code not in (429, 503) or attempt == 3:
                break
            time.sleep(2 ** (attempt + 1))
        if not response.is_success:
            # Do not propagate response bodies or headers into application logs.
            raise RuntimeError(f"云端模型调用失败 HTTP {response.status_code}")
        data = response.json()["choices"][0]["message"]
        calls = []
        for call in data.get("tool_calls") or []:
            args = json.loads(call["function"]["arguments"])
            if not isinstance(args, dict):
                raise ValueError("工具参数必须为对象")
            calls.append({"name": call["function"]["name"], "args": args, "id": call["id"]})
        return AIMessage(content=data.get("content") or "", tool_calls=calls)


def create_chat_model():
    if settings.model_provider == "cloud":
        return CloudChatModel()
    from langchain_ollama import ChatOllama
    return ChatOllama(
        model=settings.ollama_model, base_url=settings.ollama_base_url,
        temperature=0, reasoning=settings.ollama_reasoning,
        num_ctx=settings.ollama_num_ctx, num_predict=settings.ollama_num_predict,
        client_kwargs={"timeout": settings.ollama_timeout_seconds},
    )
