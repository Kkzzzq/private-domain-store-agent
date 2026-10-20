from datetime import timedelta
from hashlib import sha256
import re

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import settings
from app.models.quality import QualityPlan, QualityRun, QualityResult
from app.models.tables import utcnow
from app.quality.catalog import content_digest
from app.quality.service import run_out


TERMINAL = {"completed", "failed", "blocked", "cancelled"}
RETENTION_LIMIT = 200
# 报告保留策略：已结束的运行及其不再被引用的截图，保留 7 天后自动删除。
# 计划与活动任务永不自动删除（历史结论可复核，代码指纹仍能解释旧报告）。
RETENTION_DAYS = 7


def compare(db, baseline, candidate):
    first, second = run_out(db, baseline), run_out(db, candidate)
    dimensions = ["environment_id", "fixture_version"]
    reasons = [key for key in dimensions if first["target"].get(key) != second["target"].get(key)]
    if first["mode"] != second["mode"]:
        reasons.append("mode")
    if baseline.status not in TERMINAL or candidate.status not in TERMINAL:
        reasons.append("unfinished_run")
    old = {row["id"]: row for row in first["results"]}
    new = {row["id"]: row for row in second["results"]}
    versions = [{row["id"]: content_digest(row) for row in report["target"].get("case_snapshots") or []} for report in (first, second)]
    rows = []
    for case_id in sorted(old.keys() | new.keys()):
        before, after = old.get(case_id), new.get(case_id)
        comparable = not reasons and before is not None and after is not None and versions[0].get(case_id) == versions[1].get(case_id) and case_id in versions[0]
        transition = "not_comparable"
        if comparable:
            transition = "regressed" if before["status"] == "passed" and after["status"] != "passed" else "improved" if before["status"] != "passed" and after["status"] == "passed" else "unchanged"
        rows.append({"id": case_id, "before": before["status"] if before else "not_selected", "after": after["status"] if after else "not_selected", "comparable": comparable, "transition": transition})
    return {"baseline": baseline.id, "candidate": candidate.id, "incompatible_dimensions": reasons, "cases": rows,
            "groups": {"baseline": baseline.summary.get("groups", {}), "candidate": candidate.summary.get("groups", {})},
            "note": "不同环境、模式或用例版本不判定回归；目标代码版本允许不同，供版本对照。"}


def artifact_path(artifact_id):
    if not re.fullmatch(r"[a-f0-9]{32}\.png", artifact_id):
        raise HTTPException(404, "截图不存在")
    root = (settings.backend_root / "data" / "quality-artifacts").resolve()
    path = (root / artifact_id).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(404, "截图不存在")
    return path


def owned_artifact(db, run_id, artifact_id):
    rows = db.scalars(select(QualityResult).where(QualityResult.run_id == run_id)).all()
    declared = next((item for row in rows for item in row.evidence.get("artifacts", []) if item.get("id") == artifact_id), None)
    path = artifact_path(artifact_id)
    if not declared or not path.is_file() or sha256(path.read_bytes()).hexdigest() != declared.get("sha256"):
        raise HTTPException(404, "截图不存在或校验失败")
    return path


def retention_preview(db, days):
    cutoff = utcnow() - timedelta(days=days)
    scope = (QualityRun.status.in_(TERMINAL), QualityRun.created_at < cutoff)
    total = db.scalar(select(func.count()).select_from(QualityRun).where(*scope)) or 0
    runs = db.scalars(select(QualityRun).where(*scope).order_by(QualityRun.created_at).limit(RETENTION_LIMIT)).all()
    snapshot = [{"id": row.id, "status": row.status, "created_at": row.created_at.isoformat()} for row in runs]
    remaining = max(0, total - len(snapshot))
    return {"days": days, "count": len(snapshot), "total": total, "truncated": remaining > 0, "remaining": remaining, "runs": snapshot,
            "digest": content_digest({"days": days, "runs": snapshot}),
            "notice": f"最多{RETENTION_LIMIT}条，仅删除已结束的历史运行及不再引用的截图；计划和活动任务保留。"}


def retention_apply(db, days, digest):
    preview = retention_preview(db, days)
    if preview["digest"] != digest:
        raise HTTPException(409, "清理范围已变化，请重新预览")
    ids = [row["id"] for row in preview["runs"]]
    rows = db.scalars(select(QualityResult).where(QualityResult.run_id.in_(ids))).all() if ids else []
    artifacts = {item.get("id") for row in rows for item in row.evidence.get("artifacts", [])}
    for row in rows:
        db.delete(row)
    for run_id in ids:
        db.delete(db.get(QualityRun, run_id))
    db.commit()
    remaining = {item.get("id") for row in db.scalars(select(QualityResult)) for item in row.evidence.get("artifacts", [])}
    failed = []
    for artifact_id in artifacts - remaining:
        try:
            artifact_path(artifact_id).unlink(missing_ok=True)
        except Exception:
            failed.append("截图清理失败")
    return {"deleted_runs": len(ids), "artifact_cleanup_errors": failed, "plans_preserved": True}


def retention_auto(db, days=None):
    """按保留策略自动清理超期报告（默认 7 天）。

    只删已结束的运行与不再被引用的截图；计划、活动任务与仍被引用的截图保留。
    由 worker 定时调用，也可在运维脚本里直接调。
    """
    days = RETENTION_DAYS if days is None else days
    preview = retention_preview(db, days)
    if not preview["count"]:
        return {"days": days, "deleted_runs": 0, "artifact_cleanup_errors": [], "plans_preserved": True}
    done = retention_apply(db, days, preview["digest"])
    return {"days": days, **done}
