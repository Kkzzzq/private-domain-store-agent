import json
import time
import hashlib
import atexit
from threading import Lock

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.credentials import cloud_api_key


_quota_cooldowns = {}
_quota_lock = Lock()
cloud_http = httpx.Client(limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60))
atexit.register(cloud_http.close)


def quota_exhausted(response):
    if response.is_success:
        return False
    try:
        code = str(response.json().get("error", {}).get("code"))
        return code in ({"1113", "1308", "1310"} if settings.cloud_api_style == "zhipu" else {"AllocationQuota.FreeTierOnly", "QuotaExhausted", "QuotaExceeded"})
    except (ValueError, AttributeError):
        return False


class CloudChatModel:
    """Cloud API adapter; credentials stay in backend configuration."""

    def __init__(self, tools=None):
        self.tools = tools or []

    def bind_tools(self, tools):
        from langchain_core.utils.function_calling import convert_to_openai_tool
        return CloudChatModel([convert_to_openai_tool(tool) for tool in tools])

    def invoke(self, messages):
        from langchain_core.messages import convert_to_openai_messages
        api_key = cloud_api_key()
        if not settings.cloud_base_url:
            raise RuntimeError("云端模型未配置")
        converted = convert_to_openai_messages(messages)
        for original, converted_message in zip(messages, converted):
            reasoning = getattr(original, "additional_kwargs", {}).get("reasoning_content")
            if reasoning and converted_message["role"] == "assistant":
                converted_message["reasoning_content"] = reasoning
        models = list(dict.fromkeys([settings.cloud_model] + [name.strip() for name in settings.cloud_fallback_models.split(",") if name.strip()]))
        if len(models) > 5:
            raise RuntimeError("云端模型候选数量不能超过5个")
        credential_scope = hashlib.sha256(api_key.encode()).hexdigest()
        for model_name in models:
            scope = (settings.cloud_base_url, settings.cloud_api_style, credential_scope, model_name)
            with _quota_lock:
                if _quota_cooldowns.get(scope, 0) > time.monotonic():
                    continue
                _quota_cooldowns.pop(scope, None)
            body = {"model": model_name, "messages": converted, "temperature": 0,
                    "max_tokens": settings.cloud_max_tokens}
            if settings.cloud_api_style == "zhipu":
                if model_name.startswith("glm-5.3"):
                    body["thinking"] = {"type": "enabled", "clear_thinking": False}
                    body["reasoning_effort"] = "low"
                    body["temperature"] = 1
                else:
                    body["thinking"] = {"type": "disabled"}
            elif settings.cloud_api_style == "deepseek":
                body["thinking"] = {"type": "disabled"}
            else:
                body["enable_thinking"] = False
            if self.tools:
                body["tools"] = self.tools
            for attempt in range(4):
                response = cloud_http.post(
                    settings.cloud_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + api_key},
                    json=body, timeout=settings.cloud_timeout_seconds,
                )
                if quota_exhausted(response) or response.status_code not in (429, 503) or attempt == 3:
                    break
                time.sleep(2 ** (attempt + 1))
            if quota_exhausted(response):
                with _quota_lock:
                    _quota_cooldowns[scope] = time.monotonic() + settings.cloud_fallback_cooldown_seconds
                logger.warning("Cloud model quota exhausted; model=%s; trying configured next model", model_name)
                continue
            if not response.is_success:
                raise RuntimeError(f"云端模型调用失败 HTTP {response.status_code}")
            if model_name != settings.cloud_model:
                logger.info("Cloud model fallback selected; model=%s", model_name)
            return self.parse_message(response.json()["choices"][0]["message"], model_name)
        raise RuntimeError("云端模型额度不足，所有候选模型均不可用或处于额度冷却期")

    def parse_message(self, data, model_name):
        from langchain_core.messages import AIMessage
        calls = []
        for call in data.get("tool_calls") or []:
            args = json.loads(call["function"]["arguments"])
            if not isinstance(args, dict):
                raise ValueError("工具参数必须为对象")
            calls.append({"name": call["function"]["name"], "args": args, "id": call["id"]})
        extra = {"reasoning_content": data["reasoning_content"]} if data.get("reasoning_content") else {}
        return AIMessage(content=data.get("content") or "", tool_calls=calls, additional_kwargs=extra,
                         response_metadata={"model": model_name})


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
