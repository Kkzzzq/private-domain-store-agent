import json
import os
import re
from time import perf_counter


def safe(value, depth=0):
    if depth > 7:
        return "[深层数据省略]"
    if isinstance(value, dict):
        metrics = {"tokens", "max_tokens", "total_tokens", "input_tokens", "output_tokens"}
        return {str(key): "[已脱敏]" if str(key).lower() not in metrics and any(term in str(key).lower() for term in ("password", "token", "authorization", "secret", "api_key", "phone", "address", "receiver")) else safe(item, depth + 1) for key, item in list(value.items())[:70]}
    if isinstance(value, (list, tuple)):
        selected = [safe(item, depth + 1) for item in value[:150]]
        if len(value) > 150:
            selected.append({"evidence_truncated": True, "total": len(value)})
        return selected
    if isinstance(value, str):
        text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_=-]+", "[令牌已脱敏]", value)
        text = re.sub(r"(?<!\d)1\d{10}(?!\d)", "[手机号已脱敏]", text)
        return text[:16000]
    return value


from app.core.sqlite_runtime import ensure_sqlite


def configure_environment():
    if not re.fullmatch(r"[a-f0-9]{32}", os.environ.get("QA_CHILD_RUN", "")):
        raise RuntimeError("缺少隔离执行标记")
    ensure_sqlite()
    from pathlib import Path
    import shutil
    # 上传与页面资源也要隔离，不能让测试图片写进业务站点的 uploads。
    source_web = Path(__file__).resolve().parents[3] / "web"
    target_web = Path(os.environ["QA_CHILD_WORKSPACE"]) / "web"
    shutil.copytree(source_web, target_web, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("uploads", "node_modules", ".git"))
    os.environ.update(DATABASE_URL="sqlite://", REDIS_URL="memory", STRICT_DEPENDENCIES="false",
                      AGENT_MODE="fallback", AGENT_REQUIRE_LLM="false", RAG_REQUIRE_VECTORS="false",
                      JWT_SECRET=os.urandom(32).hex(), CHROMA_PATH=os.environ["QA_CHILD_WORKSPACE"] + "/chroma",
                      CLOUD_FALLBACK_MODELS="", CLOUD_TIMEOUT_SECONDS="20", AGENT_MAX_STEPS="4",
                      RECOMMENDATION_MAX_STEPS="6", AUTH_LOGIN_LIMIT="120", AUTH_REGISTER_LIMIT="50")
    if os.environ.get("QA_NATIVE_DATABASE_URL"):
        from sqlalchemy.engine import make_url
        url = make_url(os.environ["QA_NATIVE_DATABASE_URL"])
        if url.drivername != "mysql+pymysql" or url.host != "127.0.0.1" or url.port != 13306 or not re.fullmatch(r"qa_[a-f0-9]{32}", url.database or "") or not re.fullmatch(r"qa:[a-f0-9]{32}:", os.environ.get("QA_NATIVE_PREFIX", "")):
            raise RuntimeError("原生测试档隔离校验失败")
        os.environ.update(DATABASE_URL=os.environ["QA_NATIVE_DATABASE_URL"], REDIS_URL="redis://127.0.0.1:16379/0", STRICT_DEPENDENCIES="true")


def configure_test_model(target=False):
    if not re.fullmatch(r"[a-f0-9]{32}", os.environ.get("QA_CHILD_RUN", "")):
        raise RuntimeError("测试模型只能用于隔离子进程")
    from app.core.config import settings
    if target:
        if settings.qa_target_chat_model:
            if not settings.qa_target_chat_api_key_file or not settings.qa_target_chat_base_url:
                raise RuntimeError("被测模型实验配置缺少独立端点或密钥文件")
            settings.model_provider = "cloud"
            settings.cloud_model = settings.qa_target_chat_model
            settings.cloud_base_url = settings.qa_target_chat_base_url
            settings.cloud_api_style = settings.qa_target_chat_api_style
            settings.cloud_api_key = ""
            settings.cloud_api_key_file = settings.qa_target_chat_api_key_file
            settings.cloud_fallback_models = ""
        return
    if settings.qa_chat_model:
        if not settings.qa_chat_api_key_file:
            raise RuntimeError("测试模型未配置独立密钥文件")
        settings.model_provider = "cloud"
        settings.cloud_model = settings.qa_chat_model
        settings.cloud_base_url = settings.qa_chat_base_url
        settings.cloud_api_style = settings.qa_chat_api_style
        settings.cloud_api_key = ""
        settings.cloud_api_key_file = settings.qa_chat_api_key_file
        settings.cloud_fallback_models = ""


class Evidence:
    def __init__(self):
        self.requests = []
        self.assertions = []

    def check(self, name, condition, expected=None, actual=None):
        self.assertions.append({"name": name, "passed": bool(condition), "expected": safe(expected), "actual": safe(actual)})
        if not condition:
            raise AssertionError(name)

    def install(self):
        from starlette.testclient import TestClient
        original = TestClient.request
        def request(client, method, url, *args, **kwargs):
            started = perf_counter()
            response = original(client, method, url, *args, **kwargs)
            try:
                output = response.json()
            except ValueError:
                output = "[非JSON响应]"
            if len(self.requests) < 150:
                self.requests.append({"method": method, "path": str(url).split("?")[0],
                                      "input": safe(kwargs.get("json")), "status": response.status_code,
                                      "output": safe(output), "elapsed_ms": round((perf_counter() - started) * 1000)})
            return response
        TestClient.request = request
        return lambda: setattr(TestClient, "request", original)


class ModelBudget:
    def __init__(self, max_calls, max_tokens):
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.calls = 0
        self.tokens = 0
        self.models = []
        self.estimated = False
        self.exhausted = False

    def install(self):
        from app.agent.model import cloud_http
        import httpx
        from app.core.config import settings
        if settings.model_provider != "cloud":
            raise RuntimeError("首期真实模型预算适配仅支持已配置云端模型")
        original = cloud_http.post
        original_embedding = httpx.post
        def measured(send, url, *args, **kwargs):
            body = kwargs.get("json", {})
            reserve = len(json.dumps(body, ensure_ascii=False).encode()) + int(body.get("max_tokens", 2048))
            if self.calls >= self.max_calls or self.tokens + reserve > self.max_tokens:
                self.exhausted = True
                raise RuntimeError("质量任务模型预算已耗尽")
            self.calls += 1
            self.tokens += reserve
            try:
                response = send(url, *args, **kwargs)
            except Exception:
                self.estimated = True
                raise
            try:
                payload = response.json()
            except ValueError:
                self.estimated = True
                return response
            usage = payload.get("usage", {}).get("total_tokens")
            if isinstance(usage, int) and usage >= 0:
                self.tokens += usage - reserve
            elif not response.is_success:
                self.estimated = True
            else:
                self.estimated = True
            self.models.append({"model": body.get("model"), "http_status": response.status_code, "kind": "embedding" if str(url).endswith(("/embeddings", "/multimodal-embedding")) else "chat"})
            return response
        cloud_http.post = lambda url, *args, **kwargs: measured(original, url, *args, **kwargs)
        httpx.post = lambda url, *args, **kwargs: measured(original_embedding, url, *args, **kwargs) if str(url).endswith(("/embeddings", "/multimodal-embedding")) else original_embedding(url, *args, **kwargs)
        def restore():
            cloud_http.post = original
            httpx.post = original_embedding
        return restore

    def output(self):
        return {"calls": self.calls, "tokens": self.tokens, "max_calls": self.max_calls, "max_tokens": self.max_tokens,
                "exhausted": self.exhausted, "estimated": self.estimated, "models": self.models,
                "scope": "本子进程云端聊天与Embedding请求；缺usage时保留UTF8字节+输出上限保守预留"}
