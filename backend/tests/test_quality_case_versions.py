from app.db.session import SessionLocal
from app.models.quality import QualityPlan
from test_quality import operator, launch


def definition(message="搜索抱枕"):
    return {"title": "自定义抱枕搜索", "role": "customer", "turns": [{"message": message, "required_tools": ["search_products"], "expected_contains": ["抱枕"]}]}


def test_case_version_review_immutable_snapshots_and_revocation(client):
    headers, _user_id = operator(client)
    draft = client.post("/api/v1/op/qa/cases", headers=headers, json=definition()).json()
    plan_body = {"goal": "自定义版本验收", "kind": "assistant", "mode": "live", "case_ids": [draft["id"]]}
    assert client.post("/api/v1/op/qa/plans", headers=headers, json=plan_body).status_code == 422
    assert client.post(f"/api/v1/op/qa/cases/{draft['id']}/approve", headers=headers, json={"digest": "0"*64}).status_code == 409
    approved = client.post(f"/api/v1/op/qa/cases/{draft['id']}/approve", headers=headers, json={"digest": draft["revision_digest"]}).json()
    assert approved["state"] == "active"
    assert client.patch(f"/api/v1/op/qa/cases/{draft['id']}", headers=headers, json=definition("搜索杯子")).status_code == 409
    planned = client.post("/api/v1/op/qa/plans", headers=headers, json=plan_body).json()
    assert planned["payload"]["case_snapshots"][0]["definition"] == draft["definition"]
    revised = client.post(f"/api/v1/op/qa/cases/{draft['id']}/revisions", headers=headers, json=definition("搜索杯子")).json()
    assert revised["version"] == 2 and revised["state"] == "candidate" and revised["family_id"] == draft["family_id"]
    with SessionLocal() as db:
        assert db.get(QualityPlan, planned["id"]).payload["case_snapshots"][0]["version"] == 1
    assert client.post(f"/api/v1/op/qa/plans/{planned['id']}/approve", headers=headers, json={"digest": planned["digest"]}).status_code == 200
    assert client.post(f"/api/v1/op/qa/cases/{draft['id']}/revoke", headers=headers, json={}).status_code == 200
    assert client.post("/api/v1/op/qa/runs", headers=headers, json={"plan_id": planned["id"], "request_key": "revoked-case"}).status_code == 409


def test_custom_case_no_arbitrary_code_url_or_unregistered_tool(client):
    headers, _user_id = operator(client)
    for body in [{**definition(), "code": "print(1)"}, {**definition(), "url": "https://example.test"},
                 {**definition(), "turns": [{"message": "测试任意工具", "required_tools": ["execute_sql"]}]},
                 {**definition(), "turns": [{"message": "没有断言的测试"}]}]:
        assert client.post("/api/v1/op/qa/cases", headers=headers, json=body).status_code == 422
    headers, _user_id = operator(client, {"qa.view"})
    assert client.post("/api/v1/op/qa/cases", headers=headers, json=definition()).status_code == 403
