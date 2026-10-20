from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tables import AgentToolLog, User
from app.quality.case_versions import execute_definition
from app.quality.sandbox import Evidence
from app.quality.service import fingerprint
from app.quality import service


def test_documentation_changes_preserve_fingerprint_but_executor_changes_do_not(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "settings", SimpleNamespace(backend_root=tmp_path))
    source = tmp_path / "app" / "quality"
    source.mkdir(parents=True)
    documentation = source / "case_docs_assistant_a.py"
    executor = source / "case_versions.py"
    documentation.write_text("DOCS = {}", encoding="utf-8")
    executor.write_text("version = 1", encoding="utf-8")
    original = fingerprint()
    for name in ("case_docs.py", "case_docs_assistant_a.py", "case_docs_assistant_b.py",
                 "case_docs_functional.py", "case_docs_browser.py", "case_docs_op.py"):
        (source / name).write_text("DOCS = {'A01': 'new wording'}", encoding="utf-8")
        assert fingerprint() == original, name
    executor.write_text("version = 2", encoding="utf-8")
    assert fingerprint() != original


@pytest.mark.parametrize("audit_kind", ["success", "denied", "missing", "foreign_user", "foreign_session", "previous_turn"])
def test_custom_tool_assertions_require_current_scoped_successful_audit(client, monkeypatch, audit_kind):
    original = TestClient.request
    monkeypatch.setattr(settings, "agent_mode", settings.agent_mode)
    monkeypatch.setattr(settings, "agent_require_llm", settings.agent_require_llm)
    with SessionLocal() as db:
        alice = db.scalar(select(User.id).where(User.username == "alice"))
        merchant = db.scalar(select(User.id).where(User.username == "merchant"))
        if audit_kind == "previous_turn":
            db.add(AgentToolLog(user_id=alice, shop_id=1, session_id="custom-session",
                                tool="search_products", args="{}", ok=True, latency_ms=1, flag=""))
            db.commit()

    def request(test_client, method, url, *args, **kwargs):
        if str(url).endswith("/chat"):
            if audit_kind not in ("missing", "previous_turn"):
                with SessionLocal() as db:
                    db.add(AgentToolLog(user_id=merchant if audit_kind == "foreign_user" else alice,
                                       shop_id=1, session_id="foreign" if audit_kind == "foreign_session" else "custom-session",
                                       tool="search_products", args="{}", ok=audit_kind != "denied",
                                       latency_ms=1, flag="catalog_required" if audit_kind == "denied" else ""))
                    db.commit()
            return httpx.Response(200, json={"session_id": "custom-session", "mode": "llm",
                                            "answer": "抱枕", "products": [],
                                            "tools": [{"tool": "search_products", "result": "成功找到抱枕"}]})
        return original(test_client, method, url, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", request)
    evidence = Evidence()
    definition = {"title": "工具执行边界", "turns": [{"message": "搜索抱枕", "required_tools": ["search_products"]}]}
    if audit_kind == "success":
        output = execute_definition(definition, evidence)
        assert output["transcript"][0]["tool_audit"][0]["ok"] is True
        assert all(row["passed"] for row in evidence.assertions)
    else:
        with pytest.raises(AssertionError, match="必需工具"):
            execute_definition(definition, evidence)
        assert evidence.assertions[-1]["passed"] is False
