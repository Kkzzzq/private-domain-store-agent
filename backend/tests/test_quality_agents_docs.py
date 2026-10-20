"""新改版的验收门禁：用例文档完整性、/agents 契约、7 天保留策略。

这些断言刻意对着「用户看得到的东西」：每个已接入用例都要有步骤/预期/真实代码文件，
三类 Agent 都要能被 /agents 描述清楚，报告保留策略要是 7 天且自动清理不动计划。
"""
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.quality import QualityPlan, QualityRun
from app.models.tables import utcnow
from app.quality.catalog import cases
from app.quality.case_docs import CASE_DOCS, doc_for, missing_docs
from app.quality.reporting import RETENTION_DAYS, retention_auto
from test_quality import operator, plan
from test_quality_reporting import recorded_run

ROOT = Path(__file__).resolve().parents[2]


def test_every_active_case_documents_steps_expected_and_real_code_file():
    active = [row["id"] for row in cases() if row["state"] == "active"]
    assert len(active) == 74, "接入用例数量变化时请同步用例文档"
    assert missing_docs(active) == [], "有用例缺少人工登记的步骤/预期"
    for case_id in active:
        doc = doc_for(case_id)
        assert doc["steps"], case_id
        assert doc["expected"], case_id
        assert doc["risk"] in {"read-only", "writes"}, case_id
        assert doc["code_node"], case_id
        assert (ROOT / doc["code_file"]).is_file(), f"{case_id} 的代码文件不存在：{doc['code_file']}"


def test_case_docs_cover_all_three_families_and_only_known_cases():
    known = {row["id"] for row in cases()}
    assert {"A01", "A40", "F01", "F30", "E01", "E04"} <= set(CASE_DOCS)
    assert set(CASE_DOCS) <= known, "文档里出现了目录中不存在的用例"


def test_agents_endpoint_describes_three_agents_with_live_stats(client):
    headers, _ = operator(client)
    response = client.get("/api/v1/op/qa/agents", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["retention_days"] == 7
    agents = {row["id"]: row for row in payload["agents"]}
    assert set(agents) == {"business", "evaluator", "functional"}
    for row in agents.values():
        for key in ("name", "role", "purpose", "entry_points", "how_to_use", "how_to_modify", "sources", "guardrails", "stats"):
            assert row[key], f"{row['id']} 缺少 {key}"
        assert row["stats"]["active_cases"] > 0
        assert row["stats"]["documented_cases"] == row["stats"]["active_cases"]
    assert agents["business"]["tools"], "业务 Agent 必须列出真实工具清单"
    assert agents["functional"]["tools"] == [], "固定回归不该声明模型工具"


def test_cases_endpoint_exposes_steps_expected_and_code_file(client):
    headers, _ = operator(client)
    rows = client.get("/api/v1/op/qa/cases", headers=headers).json()
    assert len(rows) >= 74
    for row in rows:
        doc = row["doc"]
        assert doc["steps"] and doc["expected"], row["id"]
        assert doc["code_file"].startswith("backend/"), row["id"]


def test_cases_and_agents_need_quality_permission(client):
    from test_bc_link import login

    assert client.get("/api/v1/op/qa/agents").status_code == 401
    merchant = login(client, "merchant")
    assert client.get("/api/v1/op/qa/agents", headers=merchant).status_code == 403
    assert client.get("/api/v1/op/qa/cases", headers=merchant).status_code == 403


def test_retention_is_seven_days_and_auto_purge_keeps_plans_and_active_runs(client):
    assert RETENTION_DAYS == 7
    headers, user_id = operator(client)
    old = recorded_run(client, headers, user_id, age=90)
    recent = recorded_run(client, headers, user_id)
    active = recorded_run(client, headers, user_id, age=90)
    with SessionLocal() as db:
        db.get(QualityRun, active).status = "running"
        plans_before = {row for row in db.scalars(select(QualityPlan.id))}
        db.commit()
        result = retention_auto(db)
    assert result["days"] == 7
    assert result["deleted_runs"] == 1
    assert result["plans_preserved"] is True
    with SessionLocal() as db:
        assert db.get(QualityRun, old) is None
        assert db.get(QualityRun, recent) is not None
        assert db.get(QualityRun, active) is not None
        assert {row for row in db.scalars(select(QualityPlan.id))} == plans_before


def test_auto_purge_is_idempotent_when_nothing_expired(client):
    headers, _ = operator(client)
    recorded_run(client, headers, _)
    with SessionLocal() as db:
        first = retention_auto(db)
        second = retention_auto(db)
    assert first["deleted_runs"] == 0
    assert second["deleted_runs"] == 0


def test_platform_operators_get_full_quality_capabilities(client):
    """平台运营＝平台管理员：启动补齐后必须能看到全部质量信息，且不牵连普通账号。"""
    from app.models.operations import Operator
    from app.models.quality import QualityGrant
    from app.models.tables import User
    from app.quality.catalog import CAPABILITIES
    from app.quality.service import provision_operators

    headers, user_id = operator(client, [])
    with SessionLocal() as db:
        assert db.get(QualityGrant, user_id).capabilities == []
        assert provision_operators(db) >= 1
        assert set(db.get(QualityGrant, user_id).capabilities) == set(CAPABILITIES)
        buyer = db.scalar(select(User).where(User.username == "alice"))
        assert db.get(Operator, buyer.id) is None
        assert db.get(QualityGrant, buyer.id) is None
        assert provision_operators(db) == 0, "已补齐的账号不应被重复计数"
    assert client.get("/api/v1/op/qa/agents", headers=headers).status_code == 200
    assert client.get("/api/v1/op/qa/cases", headers=headers).status_code == 200
    assert client.get("/api/v1/op/qa/capabilities", headers=headers).json()["capabilities"] == sorted(CAPABILITIES)


def test_operator_without_grant_is_still_refused_until_provisioned(client):
    """补齐只发生在启动/显式调用：运行中新建的受限运营仍按能力位判定（保持分离设计）。"""
    headers, _ = operator(client, ["qa.view"])
    assert client.get("/api/v1/op/qa/agents", headers=headers).status_code == 200
    assert client.post("/api/v1/op/qa/plans", headers=headers, json={"goal": "库存检查", "kind": "assistant", "case_ids": ["A02"]}).status_code == 403


def test_plan_still_runs_after_case_docs_are_added(client):
    """文案不该影响执行指纹：文档化之后，原计划仍可批准并建运行。"""
    headers, _ = operator(client)
    created = plan(client, headers)
    digest = created["digest"]
    assert client.post(f"/api/v1/op/qa/plans/{created['id']}/approve", headers=headers, json={"digest": digest}).status_code == 200
    run = client.post("/api/v1/op/qa/runs", headers=headers, json={"plan_id": created["id"], "request_key": uuid4().hex})
    assert run.status_code == 201, run.text