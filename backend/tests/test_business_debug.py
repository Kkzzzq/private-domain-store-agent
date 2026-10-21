from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.quality import QualityCaseVersion, QualityPlan, QualityRun
from app.quality.sandbox import configure_test_model
from app.core.config import settings
from test_quality import operator


def test_dialogue_is_not_a_case_and_requires_live_evidence(client, monkeypatch):
    headers, _ = operator(client)
    seen = []
    def execute(spec, cancelled):
        seen.append(spec)
        assert cancelled() is False
        return {"status": "passed", "cleanup_ok": True, "budget": {"calls": 2, "tokens": 100},
                "requests": [{"path": "/chat", "status": 200, "output": {"mode": "llm"}}]}
    monkeypatch.setattr("app.quality.worker.subprocess_job", execute)
    response = client.post("/api/v1/op/qa/business-debug", headers=headers,
                           json={"role": "customer", "messages": ["搜索抱枕"], "confirmed": True})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert seen[0]["mode"] == "live" and seen[0]["case_id"] == "__business_debug__"
    assert seen[0]["environment_id"] == "isolated-local"
    assert client.get("/api/v1/op/qa/business-debug", headers=headers).json()[0]["id"] == response.json()["id"]
    with SessionLocal() as db:
        for model in (QualityCaseVersion, QualityPlan, QualityRun):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_debug_rejects_missing_permissions_arbitrary_targets_and_no_model(client, monkeypatch):
    headers, _ = operator(client, ["qa.view"])
    body = {"role": "customer", "messages": ["查询库存"], "confirmed": True}
    assert client.post("/api/v1/op/qa/business-debug", headers=headers, json=body).status_code == 403
    headers, _ = operator(client)
    for change in ({"role": "admin"}, {"confirmed": False}, {"base_url": "https://evil.test"},
                   {"messages": []}, {"messages": ["a"]}, {"user_id": 1}):
        assert client.post("/api/v1/op/qa/business-debug", headers=headers, json={**body, **change}).status_code == 422
    monkeypatch.setattr("app.quality.worker.subprocess_job", lambda *args: {"status": "passed", "cleanup_ok": True, "budget": {"calls": 0}})
    assert client.post("/api/v1/op/qa/business-debug", headers=headers, json=body).json()["status"] == "blocked"


def test_testing_profile_replaces_chat_only_with_no_paid_fallback(monkeypatch):
    for name in ("model_provider", "cloud_model", "cloud_base_url", "cloud_api_style", "cloud_api_key", "cloud_api_key_file", "cloud_fallback_models"):
        monkeypatch.setattr(settings, name, getattr(settings, name))
    monkeypatch.setenv("QA_CHILD_RUN", "a" * 32)
    monkeypatch.setattr(settings, "qa_chat_model", "glm-4-flash")
    # 测试模型供应商显式固定，避免本机 .env 切换 QA 配置后这条断言随环境变化。
    monkeypatch.setattr(settings, "qa_chat_api_style", "zhipu")
    monkeypatch.setattr(settings, "qa_chat_api_key_file", "external-test-key.txt")
    monkeypatch.setattr(settings, "cloud_api_key", "must-not-reuse")
    embedding = (settings.embedding_provider, settings.cloud_embedding_api_key_file, settings.cloud_embedding_model)
    configure_test_model()
    assert settings.cloud_model == "glm-4-flash"
    assert settings.cloud_api_style == "zhipu"
    assert settings.cloud_api_key == "" and settings.cloud_api_key_file == "external-test-key.txt"
    assert settings.cloud_fallback_models == ""
    assert (settings.embedding_provider, settings.cloud_embedding_api_key_file, settings.cloud_embedding_model) == embedding
