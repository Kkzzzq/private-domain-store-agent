from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.quality import QualityRun, QualityResult, QualityPlan
from app.models.tables import utcnow
from test_quality import operator, plan


def test_report_date_uses_beijing_midnight_and_snapshot_documents(client):
    from datetime import datetime
    from app.quality.case_docs import CASE_DOCS
    headers, user_id = operator(client)
    ids = [recorded_run(client, headers, user_id) for _ in range(3)]
    with SessionLocal() as db:
        for key, moment in zip(ids, [datetime(2026, 10, 20, 15, 59), datetime(2026, 10, 20, 16, 0), datetime(2026, 10, 21, 16, 0)]):
            db.get(QualityRun, key).created_at = moment
        db.commit()
    response = client.get('/api/v1/op/qa/runs', headers=headers, params={'report_date': '2026-10-21'})
    assert response.status_code == 200
    assert [r['id'] for r in response.json()] == [ids[1]]
    report = response.json()[0]
    assert report['name'] == f'2026-10-21 00:00 测试报告（1条用例） · {ids[1][:6]}'
    original = report['results'][0]['doc']['steps']
    old = CASE_DOCS['A02']['steps']
    try:
        CASE_DOCS['A02']['steps'] = ['后续改版文案']
        fetched = client.get('/api/v1/op/qa/runs/' + ids[1], headers=headers).json()
        assert fetched['results'][0]['doc']['steps'] == original
    finally:
        CASE_DOCS['A02']['steps'] = old
    assert client.get('/api/v1/op/qa/runs', headers=headers, params={'report_date': 'bad-date'}).status_code == 422


def recorded_run(client, headers, user_id, status="passed", age=0, environment="isolated-local"):
    planned = plan(client, headers)
    run_id = uuid4().hex
    with SessionLocal() as db:
        saved = db.get(QualityPlan, planned["id"])
        saved.payload = {**saved.payload, "environment_id": environment}
        db.add(QualityRun(id=run_id, plan_id=saved.id, user_id=user_id, request_key=uuid4().hex,
                          kind="assistant", mode="rules", status="completed", created_at=utcnow()-timedelta(days=age), summary={"groups": {}}))
        db.flush()
        db.add(QualityResult(run_id=run_id, case_id="A02", kind="assistant", status=status, evidence={"cleanup_ok": True}))
        db.commit()
    return run_id


def test_report_compare_marks_regression_and_refuses_cross_environment(client):
    headers, user_id = operator(client)
    baseline = recorded_run(client, headers, user_id)
    candidate = recorded_run(client, headers, user_id, "failed")
    report = client.get("/api/v1/op/qa/compare", headers=headers, params={"baseline": baseline, "candidate": candidate})
    assert report.status_code == 200
    assert report.json()["cases"][0]["transition"] == "regressed"
    different = recorded_run(client, headers, user_id, environment="native-local")
    response = client.get("/api/v1/op/qa/compare", headers=headers, params={"baseline": baseline, "candidate": different}).json()
    assert "environment_id" in response["incompatible_dimensions"]
    assert not response["cases"][0]["comparable"]


def test_retention_previews_then_deletes_only_terminal_old_runs(client):
    headers, user_id = operator(client)
    old = recorded_run(client, headers, user_id, age=90)
    recent = recorded_run(client, headers, user_id)
    active = recorded_run(client, headers, user_id, age=90)
    with SessionLocal() as db:
        db.get(QualityRun, active).status = "running"
        plans_before = set(db.scalars(select(QualityPlan.id)))
        db.commit()
    preview = client.post("/api/v1/op/qa/retention/preview", headers=headers, json={"days": 30}).json()
    assert [row["id"] for row in preview["runs"]] == [old]
    assert client.post("/api/v1/op/qa/retention/apply", headers=headers, json={"days": 30, "digest": "0"*64}).status_code == 409
    response = client.post("/api/v1/op/qa/retention/apply", headers=headers, json={"days": 30, "digest": preview["digest"]})
    assert response.json()["deleted_runs"] == 1
    with SessionLocal() as db:
        assert db.get(QualityRun, old) is None
        assert db.get(QualityRun, recent) and db.get(QualityRun, active)
        assert set(db.scalars(select(QualityPlan.id))) == plans_before


def test_retention_needs_approval_grant_and_artifact_is_run_bound(client, monkeypatch, tmp_path):
    from app.core.config import Settings
    monkeypatch.setattr(Settings, "backend_root", property(lambda self: tmp_path))
    headers, user_id = operator(client, {"qa.view"})
    assert client.post("/api/v1/op/qa/retention/preview", headers=headers, json={"days": 30}).status_code == 403
    headers, user_id = operator(client)
    run_id = recorded_run(client, headers, user_id)
    other = recorded_run(client, headers, user_id)
    artifact_id = uuid4().hex + ".png"
    root = tmp_path / "data" / "quality-artifacts"
    root.mkdir(parents=True)
    content = b"test-synthetic-png"
    (root / artifact_id).write_bytes(content)
    with SessionLocal() as db:
        row = db.scalar(select(QualityResult).where(QualityResult.run_id == run_id))
        row.evidence = {"artifacts": [{"id": artifact_id, "sha256": sha256(content).hexdigest()}]}
        db.commit()
    path = f"/api/v1/op/qa/runs/{run_id}/artifacts/{artifact_id}"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers).content == content
    assert client.get(f"/api/v1/op/qa/runs/{other}/artifacts/{artifact_id}", headers=headers).status_code == 404
    assert client.get(f"/api/v1/op/qa/runs/{run_id}/artifacts/not-a-uuid.png", headers=headers).status_code == 404
