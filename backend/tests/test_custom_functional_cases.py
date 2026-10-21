import pytest
from pydantic import ValidationError

from app.quality.functional_cases import execute_functional
from app.quality.sandbox import Evidence
from app.quality.service import PlanIn
from test_quality import operator


def definition():
    return {"kind": "functional", "title": "匿名购物车权限", "steps": [
        {"action": "catalog", "role": "anonymous", "expected_status": 200},
        {"action": "cart", "role": "anonymous", "expected_status": 401},
        {"action": "add_cart", "role": "customer", "sku_id": 1, "quantity": 2, "expected_status": 200},
        {"action": "cart", "role": "customer", "expected_status": 200,
         "checks": [{"path": "items.0.quantity", "operator": "equals", "value": 2}]}]}


def test_functional_case_review_version_type_and_permissions(client):
    headers, _ = operator(client)
    response = client.post("/api/v1/op/qa/cases", headers=headers, json=definition())
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["kind"] == "functional" and row["adapter"] == "declarative_functional"
    plan = {"goal": "验证自建功能步骤", "kind": "functional", "case_ids": [row["id"]], "diagnostic": True}
    assert client.post("/api/v1/op/qa/plans", headers=headers, json=plan).status_code == 422
    assert client.post(f"/api/v1/op/qa/cases/{row['id']}/approve", headers=headers, json={"digest": row["revision_digest"]}).status_code == 200
    assert client.post("/api/v1/op/qa/plans", headers=headers, json=plan).status_code == 201
    assert client.post("/api/v1/op/qa/plans", headers=headers, json={**plan, "kind": "assistant", "mode": "live"}).status_code == 422
    assert client.patch(f"/api/v1/op/qa/cases/{row['id']}", headers=headers, json=definition()).status_code == 409
    revision = client.post(f"/api/v1/op/qa/cases/{row['id']}/revisions", headers=headers, json=definition()).json()
    assert revision["version"] == 2 and revision["state"] == "candidate"
    assert client.post(f"/api/v1/op/qa/cases/{row['id']}/revisions", headers=headers,
                       json={"title": "跨类型修改", "turns": [{"message": "搜索商品", "expected_contains": ["商品"]}]}).status_code == 409
    headers, _ = operator(client, ["qa.view", "qa.assistant.run"])
    assert client.post("/api/v1/op/qa/cases", headers=headers, json=definition()).status_code == 403


def test_fixed_actions_really_write_and_read_synthetic_cart(client):
    evidence = Evidence()
    restore = evidence.install()
    try:
        result = execute_functional(definition(), evidence)
    finally:
        restore()
    assert len(result["suite"]["reports"]) == 4
    assert all(row["passed"] for row in evidence.assertions)
    assert any(row["path"].endswith("/cart") and row["method"] == "POST" for row in evidence.requests)
    assert evidence.assertions[-1]["actual"] == 2


def test_functional_rejects_arbitrary_execution_and_missing_response_fields(client):
    headers, _ = operator(client)
    for step in [{"action": "shell", "command": "whoami"}, {"action": "catalog", "url": "https://evil.test"},
                 {"action": "product"}, {"action": "cart", "checks": [{"path": "x[0]", "value": 1}]}]:
        assert client.post("/api/v1/op/qa/cases", headers=headers,
                           json={"kind": "functional", "title": "非法用例", "steps": [step]}).status_code == 422
    with pytest.raises(AssertionError):
        execute_functional({"kind": "functional", "title": "字段不存在", "steps": [{"action": "cart", "checks": [{"path": "missing", "value": 1}]}]}, Evidence())


def test_formal_plans_cannot_select_rules_or_skip_real_planning():
    for values in [{"mode": "rules"}, {"planner": "fixed"}]:
        with pytest.raises(ValidationError):
            PlanIn(goal="真实模型验收", kind="assistant", case_ids=["A02"], **values)
    assert PlanIn(goal="真实助手验收", kind="assistant", case_ids=["A02"]).mode == "live"
    assert PlanIn(goal="真实功能规划", kind="functional", case_ids=["F01"]).planner == "model"
    assert PlanIn(goal="平台诊断", kind="assistant", case_ids=["A02"], diagnostic=True).planner == "fixed"
