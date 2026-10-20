"""对抗性验证：用例版本管理、报告对比、历史保留与清理（未提交第三批 WIP）。

本文件只做独立验证，不改动任何产品代码。验证对象：
- backend/app/quality/case_versions.py
- backend/app/quality/reporting.py 的 compare / retention_preview / retention_apply
- backend/app/api/quality.py 的 /cases 与 /retention 端点
- web/op-quality.js 中「审核启用 / 撤销启用 / 新建版本 / 历史清理」的能力门控（源码级核对）

每一条测试都对应任务里列出的不变量，并尽量配一个正面对照，避免“永远不可比”式的空洞断言。
"""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4
import re

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.quality import QualityCaseVersion, QualityPlan, QualityResult, QualityRun
from app.models.tables import utcnow
from app.quality.catalog import content_digest
from test_bc_link import login
from test_quality import operator, plan

QA = "/api/v1/op/qa"


# ---------------------------------------------------------------- helpers

def definition(message="搜索抱枕"):
    return {"title": "自定义抱枕搜索", "role": "customer",
            "turns": [{"message": message, "required_tools": ["search_products"], "expected_contains": ["抱枕"]}]}


def snapshot_stub(case_id, revision="r1"):
    """构造一份可比较的用例快照，用于直接操纵计划快照验证 compare 的版本判定。"""
    return {"id": case_id, "title": case_id + "标题", "kind": "assistant", "version": 1, "state": "active",
            "modes": ["rules"], "adapter": "isolated_assistant_api", "critical": True, "revision_digest": revision}


def approved_case(client, headers, message="搜索抱枕"):
    created = client.post(f"{QA}/cases", headers=headers, json=definition(message))
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["state"] == "candidate"
    approved = client.post(f"{QA}/cases/{draft['id']}/approve", headers=headers, json={"digest": draft["revision_digest"]})
    assert approved.status_code == 200, approved.text
    return approved.json()


def raw_plan(client, headers, **body):
    return client.post(f"{QA}/plans", headers=headers,
                       json={"goal": "对抗性验证计划", "kind": "assistant", "case_ids": ["A02"], **body})


def recorded_run(client, headers, user_id, results, *, status="completed", mode="rules", age=0,
                 environment="isolated-local", fixture="seed-isolated-v1", snapshots=None,
                 summary=None, plan_id=None, run_id=None):
    """直接落库一条历史运行，绕过 worker，便于精确构造对比 / 清理边界。"""
    if plan_id is None:
        plan_id = plan(client, headers)["id"]
    run_id = run_id or uuid4().hex
    with SessionLocal() as db:
        saved = db.get(QualityPlan, plan_id)
        payload = {**saved.payload, "environment_id": environment, "fixture_version": fixture}
        if snapshots is not None:
            payload["case_snapshots"] = snapshots
        saved.payload = payload
        db.add(QualityRun(id=run_id, plan_id=plan_id, user_id=user_id, request_key=uuid4().hex, kind="assistant",
                          mode=mode, status=status, created_at=utcnow() - timedelta(days=age),
                          summary={"groups": {}} if summary is None else summary))
        db.flush()
        for case_id, result_status in results.items():
            db.add(QualityResult(run_id=run_id, case_id=case_id, kind="assistant", status=result_status,
                                 evidence={"cleanup_ok": True}))
        db.commit()
    return run_id


def compare(client, headers, baseline, candidate):
    response = client.get(f"{QA}/compare", headers=headers, params={"baseline": baseline, "candidate": candidate})
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------- 1. 用例版本管理的不变量

def test_editing_active_case_creates_new_version_and_never_rewrites_old_snapshot(client):
    headers, _user_id = operator(client)
    active = approved_case(client, headers)
    original = active["definition"]

    # 已启用版本不能就地改写，必须走 revisions
    refused = client.patch(f"{QA}/cases/{active['id']}", headers=headers, json=definition("搜索杯子"))
    assert refused.status_code == 409
    with SessionLocal() as db:
        row = db.get(QualityCaseVersion, active["id"], populate_existing=True)
        assert (row.state, row.version, row.specification) == ("active", 1, original)

    # 计划冻结生成时的快照
    planned = plan(client, headers, case_ids=[active["id"]], mode="live")
    frozen = planned["payload"]["case_snapshots"][0]
    assert frozen["id"] == active["id"] and frozen["version"] == 1 and frozen["definition"] == original

    # 新建版本：新 id / version=2 / 候选态，旧行完全不动
    revised = client.post(f"{QA}/cases/{active['id']}/revisions", headers=headers, json=definition("搜索杯子")).json()
    assert revised["id"] != active["id"]
    assert (revised["version"], revised["state"], revised["family_id"]) == (2, "candidate", active["family_id"])
    assert revised["revision_digest"] != active["revision_digest"]
    with SessionLocal() as db:
        old = db.get(QualityCaseVersion, active["id"], populate_existing=True)
        assert (old.state, old.version, old.specification) == ("active", 1, original)
        assert db.get(QualityPlan, planned["id"]).payload["case_snapshots"][0]["definition"] == original

    # 绕过 API 直接篡改已启用行后，生成时的快照不再可信，运行必须被拒
    with SessionLocal() as db:
        db.get(QualityCaseVersion, active["id"]).specification = definition("搜索盘子")
        db.commit()
    approved = client.post(f"{QA}/plans/{planned['id']}/approve", headers=headers, json={"digest": planned["digest"]})
    assert approved.status_code == 200, approved.text
    blocked = client.post(f"{QA}/runs", headers=headers,
                          json={"plan_id": planned["id"], "request_key": "tampered-snapshot"})
    assert blocked.status_code == 409


def test_candidate_version_cannot_run_and_stale_digest_cannot_approve(client):
    headers, _user_id = operator(client)
    created = client.post(f"{QA}/cases", headers=headers, json=definition()).json()
    case_id = created["id"]

    # 候选版本不能被计划选中，也就无法运行
    assert raw_plan(client, headers, case_ids=[case_id], mode="live").status_code == 422
    assert raw_plan(client, headers, case_ids=["C00000000000"], mode="live").status_code == 422

    # 候选可就地编辑，因此旧摘要不得再能批准
    assert client.patch(f"{QA}/cases/{case_id}", headers=headers, json=definition("搜索杯子")).status_code == 200
    assert client.post(f"{QA}/cases/{case_id}/approve", headers=headers,
                       json={"digest": created["revision_digest"]}).status_code == 409
    current = next(row for row in client.get(f"{QA}/cases", headers=headers).json() if row["id"] == case_id)
    assert current["revision_digest"] != created["revision_digest"]
    assert current["state"] == "candidate"

    activated = client.post(f"{QA}/cases/{case_id}/approve", headers=headers,
                            json={"digest": current["revision_digest"]})
    assert activated.status_code == 200 and activated.json()["state"] == "active"
    assert client.post(f"{QA}/cases/{case_id}/approve", headers=headers,
                       json={"digest": current["revision_digest"]}).status_code == 409

    planned = plan(client, headers, case_ids=[case_id], mode="live")
    assert client.post(f"{QA}/plans/{planned['id']}/approve", headers=headers,
                       json={"digest": planned["digest"]}).status_code == 200

    # 撤销启用后：计划作废、计划也不可再建
    assert client.post(f"{QA}/cases/{case_id}/revoke", headers=headers, json={}).status_code == 200
    assert client.post(f"{QA}/runs", headers=headers,
                       json={"plan_id": planned["id"], "request_key": "revoked-case"}).status_code == 409
    assert raw_plan(client, headers, case_ids=[case_id], mode="live").status_code == 422


# ------------------------------------------- 2. 报告对比的不变量

def test_compare_only_regresses_when_dimensions_match(client):
    headers, user_id = operator(client)
    baseline = recorded_run(client, headers, user_id, {"A02": "passed"}, snapshots=[snapshot_stub("A02")])

    # 正面对照：所有维度一致时才会判回归
    regression = recorded_run(client, headers, user_id, {"A02": "failed"}, snapshots=[snapshot_stub("A02")])
    control = compare(client, headers, baseline, regression)
    assert control["incompatible_dimensions"] == []
    assert control["cases"][0]["comparable"] is True and control["cases"][0]["transition"] == "regressed"

    mismatches = (("mode", {"mode": "live"}),
                  ("fixture_version", {"fixture": "seed-isolated-v2"}),
                  ("environment_id", {"environment": "native-local"}))
    for dimension, kwargs in mismatches:
        other = recorded_run(client, headers, user_id, {"A02": "failed"}, snapshots=[snapshot_stub("A02")], **kwargs)
        report = compare(client, headers, baseline, other)
        assert dimension in report["incompatible_dimensions"], (dimension, report)
        assert not any(row["comparable"] for row in report["cases"])
        assert not any(row["transition"] in ("regressed", "improved") for row in report["cases"])

    # 任一侧未结束都必须拒绝比较，且不得输出回归
    for position in ("baseline", "candidate"):
        unfinished = recorded_run(client, headers, user_id, {"A02": "failed"}, status="running",
                                  snapshots=[snapshot_stub("A02")])
        left, right = (unfinished, baseline) if position == "baseline" else (baseline, unfinished)
        report = compare(client, headers, left, right)
        assert "unfinished_run" in report["incompatible_dimensions"], report
        assert not any(row["comparable"] for row in report["cases"])
        assert not any(row["transition"] in ("regressed", "improved") for row in report["cases"])


def test_compare_lists_added_and_removed_cases_separately(client):
    headers, user_id = operator(client)
    shared = [snapshot_stub("A02"), snapshot_stub("A03"), snapshot_stub("A04")]
    baseline = recorded_run(
        client, headers, user_id, {"A02": "passed", "A03": "failed"}, snapshots=shared,
        summary={"groups": {"assistant": {"planned": 2, "counts": {"passed": 1, "failed": 1}, "eligible": False}}})
    candidate = recorded_run(
        client, headers, user_id, {"A02": "passed", "A04": "passed"}, snapshots=shared,
        summary={"groups": {"assistant": {"planned": 2, "counts": {"passed": 2}, "eligible": True}}})
    report = compare(client, headers, baseline, candidate)

    assert report["incompatible_dimensions"] == []
    rows = {row["id"]: row for row in report["cases"]}
    assert set(rows) == {"A02", "A03", "A04"}
    # 删除的用例单独成行，不参与任何提升/回归统计
    assert rows["A03"] == {"id": "A03", "before": "failed", "after": "not_selected",
                           "comparable": False, "transition": "not_comparable"}
    # 新增的用例同样单独成行，不得把分母变化说成质量提升
    assert rows["A04"] == {"id": "A04", "before": "not_selected", "after": "passed",
                           "comparable": False, "transition": "not_comparable"}
    assert rows["A02"]["transition"] == "unchanged" and rows["A02"]["comparable"] is True
    assert not any(row["transition"] in ("improved", "regressed") for row in report["cases"] if row["id"] != "A02")

    # 两侧分组结论分开返回，没有混合通过率或单一裁决
    assert set(report["groups"]) == {"baseline", "candidate"}
    assert report["groups"]["baseline"] != report["groups"]["candidate"]
    assert not ({"pass_rate", "overall", "combined", "decision"} & set(report))


def test_compare_never_regresses_same_case_when_version_changed(client):
    headers, user_id = operator(client)
    active = approved_case(client, headers)
    frozen = {**active}
    baseline = recorded_run(client, headers, user_id, {active["id"]: "passed"}, snapshots=[frozen])

    # 正面对照：同一快照下 passed -> failed 仍应判回归
    control = compare(client, headers, baseline,
                      recorded_run(client, headers, user_id, {active["id"]: "failed"}, snapshots=[frozen]))
    assert control["cases"][0]["transition"] == "regressed"

    # 同一 id、不同版本摘要：即便 passed -> failed 也不得判回归
    changed = {**frozen, "version": 2,
               "definition": {**active["definition"], "title": active["definition"]["title"] + "改"}}
    changed["revision_digest"] = content_digest(changed["definition"])
    report = compare(client, headers, baseline,
                     recorded_run(client, headers, user_id, {active["id"]: "failed"}, snapshots=[changed]))
    assert report["incompatible_dimensions"] == []
    assert report["cases"][0]["comparable"] is False
    assert report["cases"][0]["transition"] == "not_comparable"

    # 真实 revisions 路径（新 id 同 family）：表现为新增/移除两行，同样不判回归
    revised = client.post(f"{QA}/cases/{active['id']}/revisions", headers=headers, json=definition("搜索杯子")).json()
    activated = client.post(f"{QA}/cases/{revised['id']}/approve", headers=headers,
                            json={"digest": revised["revision_digest"]})
    assert activated.status_code == 200
    family_report = compare(client, headers, baseline,
                            recorded_run(client, headers, user_id, {revised["id"]: "failed"}, snapshots=[activated.json()]))
    family_rows = {row["id"]: row for row in family_report["cases"]}
    assert set(family_rows) == {active["id"], revised["id"]}
    assert all(row["transition"] == "not_comparable" for row in family_report["cases"])
    assert not any(row["transition"] == "regressed" for row in family_report["cases"])


# ------------------------------------------- 3. 历史保留与清理的不变量

def test_retention_apply_verifies_preview_digest_and_detects_scope_drift(client):
    headers, user_id = operator(client)
    old = recorded_run(client, headers, user_id, {"A02": "passed"}, age=90)
    recent = recorded_run(client, headers, user_id, {"A02": "passed"}, age=1)
    running = recorded_run(client, headers, user_id, {"A02": "running"}, status="running", age=90)
    queued = recorded_run(client, headers, user_id, {"A02": "queued"}, status="queued", age=90)

    preview = client.post(f"{QA}/retention/preview", headers=headers, json={"days": 30}).json()
    assert [row["id"] for row in preview["runs"]] == [old]
    assert preview["count"] == 1

    # 摘要必须精确匹配：错摘要、不同保留天数一律 409，且不删除任何东西
    for body in ({"days": 30, "digest": "0" * 64}, {"days": 8, "digest": preview["digest"]}):
        assert client.post(f"{QA}/retention/apply", headers=headers, json=body).status_code == 409

    # 范围漂移：预览后新增一条符合条件的历史运行 -> 409
    drift = recorded_run(client, headers, user_id, {"A02": "passed"}, age=90)
    with SessionLocal() as db:
        plans_before = set(db.scalars(select(QualityPlan.id)))
    assert client.post(f"{QA}/retention/apply", headers=headers,
                       json={"days": 30, "digest": preview["digest"]}).status_code == 409
    with SessionLocal() as db:
        assert db.get(QualityRun, old) is not None and db.get(QualityRun, drift) is not None

    # 范围漂移：预览内的运行移出范围（completed -> running）-> 409
    with SessionLocal() as db:
        db.get(QualityRun, old).status = "running"
        db.commit()
    assert client.post(f"{QA}/retention/apply", headers=headers,
                       json={"days": 30, "digest": preview["digest"]}).status_code == 409
    with SessionLocal() as db:
        db.get(QualityRun, old).status = "completed"
        db.commit()

    fresh = client.post(f"{QA}/retention/preview", headers=headers, json={"days": 30}).json()
    assert {row["id"] for row in fresh["runs"]} == {old, drift}
    applied = client.post(f"{QA}/retention/apply", headers=headers,
                          json={"days": 30, "digest": fresh["digest"]})
    assert applied.status_code == 200, applied.text
    assert applied.json() == {"deleted_runs": 2, "artifact_cleanup_errors": [], "plans_preserved": True}

    with SessionLocal() as db:
        assert db.get(QualityRun, old) is None and db.get(QualityRun, drift) is None
        assert db.scalars(select(QualityResult).where(QualityResult.run_id.in_([old, drift]))).all() == []
        # 计划、活动任务、未到期任务、非结束态运行全部保留
        assert set(db.scalars(select(QualityPlan.id))) == plans_before
        assert db.get(QualityRun, recent) is not None
        assert db.get(QualityRun, running) is not None and db.get(QualityRun, running).status == "running"
        assert db.get(QualityRun, queued) is not None and db.get(QualityRun, queued).status == "queued"


def test_retention_deletes_only_artifacts_no_longer_referenced(client, monkeypatch, tmp_path):
    from app.core.config import Settings
    monkeypatch.setattr(Settings, "backend_root", property(lambda self: tmp_path))
    headers, user_id = operator(client)
    old = recorded_run(client, headers, user_id, {"A02": "passed"}, age=90)
    recent = recorded_run(client, headers, user_id, {"A02": "passed"}, age=1)
    shared, orphan = uuid4().hex + ".png", uuid4().hex + ".png"
    root = tmp_path / "data" / "quality-artifacts"
    root.mkdir(parents=True)
    (root / shared).write_bytes(b"shared-png")
    (root / orphan).write_bytes(b"orphan-png")
    with SessionLocal() as db:
        db.scalar(select(QualityResult).where(QualityResult.run_id == old)).evidence = {
            "cleanup_ok": True, "artifacts": [{"id": shared}, {"id": orphan}]}
        db.scalar(select(QualityResult).where(QualityResult.run_id == recent)).evidence = {
            "cleanup_ok": True, "artifacts": [{"id": shared}]}
        db.commit()

    preview = client.post(f"{QA}/retention/preview", headers=headers, json={"days": 30}).json()
    assert [row["id"] for row in preview["runs"]] == [old]
    done = client.post(f"{QA}/retention/apply", headers=headers,
                       json={"days": 30, "digest": preview["digest"]}).json()
    assert done == {"deleted_runs": 1, "artifact_cleanup_errors": [], "plans_preserved": True}
    # 仅被删除运行引用的截图被删；仍被保留运行引用的截图必须留下
    assert not (root / orphan).exists()
    assert (root / shared).is_file()
    with SessionLocal() as db:
        assert db.get(QualityRun, old) is None
        remaining = db.scalar(select(QualityResult).where(QualityResult.run_id == recent))
        assert remaining.evidence["artifacts"] == [{"id": shared}]


def test_retention_cap_200_discloses_limit_and_converges(client):
    headers, user_id = operator(client)
    planned = plan(client, headers)
    old_ids = []
    with SessionLocal() as db:
        for index in range(205):
            run_id = uuid4().hex
            old_ids.append(run_id)
            db.add(QualityRun(id=run_id, plan_id=planned["id"], user_id=user_id, request_key=uuid4().hex,
                              kind="assistant", mode="rules", status="completed",
                              created_at=utcnow() - timedelta(days=90, minutes=index), summary={"groups": {}}))
            db.flush()
            db.add(QualityResult(run_id=run_id, case_id="A02", kind="assistant", status="passed",
                                 evidence={"cleanup_ok": True}))
        db.commit()

    first = client.post(f"{QA}/retention/preview", headers=headers, json={"days": 30}).json()
    assert first["count"] == 200 and len(first["runs"]) == 200
    # 审计备注：200 上限只写在自由文本 notice 里，没有机器可读的截断标记；
    # 但重复「预览 + 应用」会收敛，不存在永久漏删。
    assert "最多200条" in first["notice"]
    assert client.post(f"{QA}/retention/apply", headers=headers,
                       json={"days": 30, "digest": first["digest"]}).json()["deleted_runs"] == 200

    second = client.post(f"{QA}/retention/preview", headers=headers, json={"days": 30}).json()
    assert second["count"] == 5
    assert client.post(f"{QA}/retention/apply", headers=headers,
                       json={"days": 30, "digest": second["digest"]}).json()["deleted_runs"] == 5

    third = client.post(f"{QA}/retention/preview", headers=headers, json={"days": 30}).json()
    assert third["count"] == 0 and third["runs"] == []
    with SessionLocal() as db:
        assert db.get(QualityRun, old_ids[0]) is None and db.get(QualityRun, old_ids[-1]) is None
        assert db.scalars(select(QualityRun)).all() == []
        assert db.get(QualityPlan, planned["id"]) is not None


# ------------------------------------------- 4. 权限不变量

def test_permissions_require_qa_approve_and_reject_bc_identities(client):
    merchant = login(client, "merchant")
    buyer = login(client, "alice")
    for headers in (merchant, buyer):
        assert client.get(f"{QA}/cases", headers=headers).status_code == 403
        assert client.post(f"{QA}/retention/preview", headers=headers, json={"days": 30}).status_code == 403
    assert client.get(f"{QA}/cases").status_code == 401
    assert client.post(f"{QA}/retention/preview", json={"days": 30}).status_code == 401
    assert client.post(f"{QA}/retention/apply", json={"days": 30, "digest": "0" * 64}).status_code == 401

    headers, user_id = operator(client)
    active = approved_case(client, headers)
    candidate = client.post(f"{QA}/cases", headers=headers, json=definition("搜索杯子")).json()
    planned = plan(client, headers)
    left = recorded_run(client, headers, user_id, {"A02": "passed"}, snapshots=[snapshot_stub("A02")])
    right = recorded_run(client, headers, user_id, {"A02": "failed"}, snapshots=[snapshot_stub("A02")])

    view_only, _ = operator(client, {"qa.view"})
    assert client.get(f"{QA}/cases", headers=view_only).status_code == 200
    assert client.get(f"{QA}/compare", headers=view_only,
                      params={"baseline": left, "candidate": right}).status_code == 200
    # 只读能力不得批准/撤销用例、批准计划、清理历史
    assert client.post(f"{QA}/cases", headers=view_only, json=definition()).status_code == 403
    assert client.post(f"{QA}/cases/{candidate['id']}/approve", headers=view_only,
                       json={"digest": candidate["revision_digest"]}).status_code == 403
    assert client.post(f"{QA}/cases/{active['id']}/revoke", headers=view_only, json={}).status_code == 403
    assert client.post(f"{QA}/plans/{planned['id']}/approve", headers=view_only,
                       json={"digest": planned["digest"]}).status_code == 403
    assert client.post(f"{QA}/retention/preview", headers=view_only, json={"days": 30}).status_code == 403
    assert client.post(f"{QA}/retention/apply", headers=view_only,
                       json={"days": 30, "digest": "0" * 64}).status_code == 403

    with SessionLocal() as db:
        assert db.get(QualityCaseVersion, active["id"], populate_existing=True).state == "active"
        assert db.get(QualityCaseVersion, candidate["id"], populate_existing=True).state == "candidate"
        assert db.get(QualityPlan, planned["id"], populate_existing=True).status == "draft"
        assert len(db.scalars(select(QualityRun)).all()) == 2


# ------------------------------------------- 5. op-quality.js 能力门控（源码级）

def test_op_quality_ui_gates_review_and_cleanup_by_capability():
    # 无浏览器运行时，只能做源码级核对：确认审核/撤销/清理入口受 qa.approve 门控，
    # 且「新建版本」对已启用用例走 /revisions 而不是就地 PATCH。
    source = Path(__file__).resolve().parents[2] / "web" / "op-quality.js"
    assert source.is_file(), source
    compact = re.sub(r"\s+", "", source.read_text(encoding="utf-8"))
    assert "can('qa.approve')&&row.state==='candidate'" in compact
    assert "can('qa.approve')&&row.state==='active'" in compact
    assert 'if(can(\'qa.approve\'))controls.append(button("历史保留与清理"' in compact
    assert "${previous.state==='candidate'?'':'/revisions'}" in compact