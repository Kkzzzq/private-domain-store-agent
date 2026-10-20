import ast
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.operations import Operator
from app.models.quality import QualityGrant, QualityPlan, QualityResult, QualityRun
from app.quality.catalog import CAPABILITIES, FUNCTIONAL_TESTS, cases
from app.quality.sandbox import safe
from app.quality.worker import run_one
from test_bc_link import login


def operator(client, caps=None):
    headers = login(client, "merchant")
    user_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        if not db.get(Operator, user_id):
            db.add(Operator(user_id=user_id))
        grant = db.get(QualityGrant, user_id)
        if grant:
            grant.capabilities = sorted(caps if caps is not None else CAPABILITIES)
        else:
            db.add(QualityGrant(user_id=user_id, capabilities=sorted(caps if caps is not None else CAPABILITIES)))
        db.commit()
    return headers, user_id


def plan(client, headers, **kwargs):
    response = client.post("/api/v1/op/qa/plans", headers=headers,
                           json={"goal": "验证助手库存与业务接口", "kind": "assistant", "case_ids": ["A02"], **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def launch(client, headers, planned, key="test-request-key"):
    approved = client.post(f"/api/v1/op/qa/plans/{planned['id']}/approve", headers=headers, json={"digest": planned["digest"]})
    assert approved.status_code == 200, approved.text
    response = client.post("/api/v1/op/qa/runs", headers=headers, json={"plan_id": planned["id"], "request_key": key})
    assert response.status_code == 201, response.text
    return response.json()


def test_quality_needs_operator_and_separate_grant(client):
    assert client.get("/api/v1/op/qa/cases").status_code == 401
    merchant = login(client, "merchant")
    assert client.get("/api/v1/op/qa/cases", headers=merchant).status_code == 403
    headers, user_id = operator(client, [])
    assert client.get("/api/v1/op/qa/runs", headers=headers).status_code == 403
    headers, user_id = operator(client, {"qa.view"})
    assert client.get("/api/v1/op/qa/cases", headers=headers).status_code == 200
    assert client.post("/api/v1/op/qa/plans", headers=headers, json={"goal": "库存检查", "kind": "assistant", "case_ids": ["A02"]}).status_code == 403


def test_quality_rejects_candidates_arbitrary_targets_and_cross_tools(client):
    headers, _user_id = operator(client)
    base = {"goal": "库存检查", "kind": "assistant", "case_ids": ["A02"]}
    for change in ({"case_ids": ["A99"]}, {"case_ids": ["A15"]}, {"environment_id": "production"}, {"base_url": "http://localhost"},
                   {"case_ids": ["F01"]}, {"case_ids": ["A02", "A02"]}, {"kind": "joint"}, {"max_tokens": 999999}):
        assert client.post("/api/v1/op/qa/plans", headers=headers, json={**base, **change}).status_code == 422


def test_plan_approval_digest_and_run_idempotency(client):
    headers, _user_id = operator(client)
    planned = plan(client, headers)
    body = {"plan_id": planned["id"], "request_key": "test-idempotency"}
    assert client.post("/api/v1/op/qa/runs", headers=headers, json=body).status_code == 409
    assert client.post(f"/api/v1/op/qa/plans/{planned['id']}/approve", headers=headers, json={"digest": "0" * 64}).status_code == 409
    first = launch(client, headers, planned, body["request_key"])
    assert client.post("/api/v1/op/qa/runs", headers=headers, json=body).json()["id"] == first["id"]
    with SessionLocal() as db:
        assert len(db.scalars(select(QualityResult).where(QualityResult.run_id == first["id"])).all()) == 1


def test_mutating_approved_content_invalidates_execution(client):
    headers, _user_id = operator(client)
    planned = plan(client, headers)
    client.post(f"/api/v1/op/qa/plans/{planned['id']}/approve", headers=headers, json={"digest": planned["digest"]})
    with SessionLocal() as db:
        stored = db.get(QualityPlan, planned["id"])
        stored.payload = {**stored.payload, "max_calls": 40}
        db.commit()
    assert client.post("/api/v1/op/qa/runs", headers=headers, json={"plan_id": planned["id"], "request_key": "tampered-plan"}).status_code == 409


def test_worker_no_fake_agent_pass_and_groups_are_independent(client):
    headers, _user_id = operator(client)
    planned = plan(client, headers, kind="joint", case_ids=["A02", "F01"])
    launched = launch(client, headers, planned)
    seen = []
    def execute(spec, cancelled):
        seen.append(spec["case_id"])
        return {"status": "passed", "cleanup_ok": True, "assertions": [{"name": "fixed", "passed": True}],
                "suite": {"reports": [{"stage": "call", "outcome": "passed"}]}}
    assert run_one(launched["id"], executor=execute)
    assert seen == ["F01", "A02"]
    report = client.get(f"/api/v1/op/qa/runs/{launched['id']}/report", headers=headers).json()
    assert report["summary"]["groups"]["functional"]["eligible"]
    assert not report["summary"]["groups"]["assistant"]["eligible"]
    assert report["summary"]["decision"] == "not_eligible"


def test_cancel_and_revoke_never_execute_new_steps(client):
    headers, user_id = operator(client)
    launched = launch(client, headers, plan(client, headers))
    client.post(f"/api/v1/op/qa/runs/{launched['id']}/cancel", headers=headers)
    def forbidden(*args, **kwargs):
        raise AssertionError("取消的任务不能执行")
    assert run_one(launched["id"], executor=forbidden)
    report = client.get(f"/api/v1/op/qa/runs/{launched['id']}", headers=headers).json()
    assert report["status"] == "cancelled" and report["results"][0]["status"] == "cancelled"
    other = launch(client, headers, plan(client, headers), "another-request-key")
    with SessionLocal() as db:
        db.get(QualityGrant, user_id).capabilities = ["qa.view"]
        db.commit()
    assert run_one(other["id"], executor=forbidden)
    report = client.get(f"/api/v1/op/qa/runs/{other['id']}", headers=headers).json()
    assert report["summary"]["decision"] == "not_eligible"


def test_registered_cases_match_existing_fixed_tests_and_redact():
    root = Path(__file__).resolve().parent
    for node in FUNCTIONAL_TESTS.values():
        filename, function = node.split("::")
        module = ast.parse((root / filename).read_text(encoding="utf-8"))
        assert function in {item.name for item in module.body if isinstance(item, ast.FunctionDef)}
    assert len(cases()) == 88 and sum(row["state"] == "active" for row in cases()) == 88
    redacted = safe({"access_token": "private", "password": "password", "phone": "13911112222"})
    assert set(redacted.values()) == {"[已脱敏]"}
    assert safe({"budget": {"tokens": 120, "calls": 2}})["budget"]["tokens"] == 120


def test_real_isolated_worker_joint_run_retains_numeric_budget(client):
    headers, _user_id = operator(client)
    launched = launch(client, headers, plan(client, headers, kind="joint", case_ids=["A02", "F01"]))
    assert run_one(launched["id"])
    report = client.get(f"/api/v1/op/qa/runs/{launched['id']}", headers=headers).json()
    assert report["summary"]["decision"] == "eligible", report
    assert report["summary"]["budget"]["tokens"] == 0
    assert all(row["evidence"]["cleanup_ok"] for row in report["results"])
    assert all(row["evidence"]["requests"] for row in report["results"])


def test_live_cannot_pass_with_rule_response_and_skipped_suite(client):
    headers, _user_id = operator(client)
    launched = launch(client, headers, plan(client, headers, kind="joint", mode="live", case_ids=["A02", "F01"]))
    def fake(spec, cancelled):
        return {"status": "passed", "cleanup_ok": True, "assertions": [{"name": "fixture", "passed": True}],
                "requests": [{"path": "/api/v1/c/shops/nanzhi/chat", "status": 200, "output": {"mode": "fallback"}}],
                "suite": {"reports": [{"stage": "call", "outcome": "skipped"}]}}
    assert run_one(launched["id"], executor=fake)
    report = client.get(f"/api/v1/op/qa/runs/{launched['id']}", headers=headers).json()
    assert all(row["status"] == "blocked" for row in report["results"])
    assert report["summary"]["decision"] == "not_eligible"


def test_revocation_is_observed_during_execution(client):
    headers, user_id = operator(client)
    launched = launch(client, headers, plan(client, headers))
    observed = []
    def execute(spec, cancelled):
        assert not cancelled()
        with SessionLocal() as db:
            db.get(QualityGrant, user_id).capabilities = ["qa.view"]
            db.commit()
        observed.append(cancelled())
        return {"status": "cancelled", "cleanup_ok": True}
    assert run_one(launched["id"], executor=execute)
    assert observed == [True]


def test_queue_lanes_separate_and_recover(client):
    from app.quality import queue
    first = queue.acquire("assistant")
    assert first and queue.acquire("assistant") is None
    other = queue.acquire("functional")
    assert other and queue.renew("assistant", first)
    queue.release("assistant", "wrong-owner")
    assert queue.acquire("assistant") is None
    queue.release("assistant", first)
    queue.release("functional", other)
    assert queue.acquire("assistant")


def test_inventory_oracle_does_not_match_partial_numbers():
    from app.quality.scenarios import matches_inventory
    assert matches_inventory("库存：**20 件**", 20)
    assert not matches_inventory("库存200件", 20)
    assert not matches_inventory("库存20件，另一个库存8件", 20)
