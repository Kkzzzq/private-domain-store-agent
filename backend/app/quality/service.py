from collections import Counter
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.core.config import settings
from app.models.operations import Operator
from app.models.quality import QualityGrant, QualityPlan, QualityResult, QualityRun
from app.quality.catalog import CATALOG_VERSION, CAPABILITIES, environments, case_by_id, content_digest


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=2, max_length=2000)
    kind: str = Field(pattern="^(assistant|functional|joint)$")
    mode: str = Field(default="rules", pattern="^(rules|live)$")
    planner: str = Field(default="fixed", pattern="^(fixed|model)$")
    environment_id: str = Field(default="isolated-local", pattern="^(isolated-local|native-local)$")
    case_ids: list[str] = Field(min_length=1, max_length=20)
    max_calls: int = Field(default=20, ge=1, le=50)
    max_tokens: int = Field(default=30000, ge=2000, le=60000)
    timeout_seconds: int = Field(default=600, ge=30, le=1200)

    @model_validator(mode="after")
    def validate_cases(self):
        if self.environment_id not in {row["id"] for row in environments()}:
            raise ValueError("测试环境尚未授权启用")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("用例不能重复")
        kinds = set()
        for case_id in self.case_ids:
            case = case_by_id(case_id)
            from app.quality.case_versions import custom_id
            if case is None and custom_id(case_id):
                case = {"kind": "assistant", "state": "active", "modes": ["live"]}
            if not case or case["state"] != "active":
                raise ValueError("只能选择已接入的审核用例")
            kinds.add(case["kind"])
            if "environments" in case and self.environment_id not in case["environments"]:
                raise ValueError(f"{case_id}不支持所选环境")
            if case["kind"] == "assistant" and self.mode not in case["modes"]:
                raise ValueError(f"{case_id}不支持所选执行模式，不能用规则兜底代替真实模型")
        if self.kind != "joint" and kinds != {self.kind}:
            raise ValueError("计划类型与用例不一致")
        if self.kind == "joint" and kinds != {"assistant", "functional"}:
            raise ValueError("联合回归必须选择两类用例")
        if self.kind == "functional" and self.mode != "rules":
            raise ValueError("功能回归使用固定执行器，不消耗被测模型")
        return self


def capabilities(db, user_id):
    grant = db.get(QualityGrant, user_id, populate_existing=True)
    if not db.get(Operator, user_id, populate_existing=True) or not grant:
        return set()
    return set(grant.capabilities) & CAPABILITIES


def require_capability(db, user_id, capability):
    if capability not in capabilities(db, user_id):
        raise HTTPException(403, "没有对应的OP质量能力授权")


def require_execution(db, user_id, kind):
    require_capability(db, user_id, "qa.view")
    for part in ("assistant", "functional") if kind == "joint" else (kind,):
        require_capability(db, user_id, f"qa.{part}.run")


def fingerprint():
    digest = sha256()
    for directory in (settings.backend_root / "app", settings.backend_root / "tests"):
        for source in sorted(directory.rglob("*.py")):
            if source.name.startswith(("op_", "test_op")) or source.name in ("operations.py", "operations_cli.py", "platform_audit.py"):
                continue
            digest.update(source.relative_to(settings.backend_root).as_posix().encode())
            digest.update(source.read_bytes())
    return digest.hexdigest()


def new_plan(db, user_id, body):
    require_execution(db, user_id, body.kind)
    from app.quality.case_versions import resolve, validate_snapshots
    snapshots = [resolve(db, case_id) for case_id in body.case_ids]
    if any(row is None or row["state"] != "active" for row in snapshots):
        raise HTTPException(422, "只能选择已审核启用的用例")
    validate_snapshots(db, snapshots)
    payload = body.model_dump()
    payload.update(catalog_version=CATALOG_VERSION, target_revision=fingerprint(),
                   fixture_version="seed-isolated-v1", environment=next(row for row in environments() if row["id"] == body.environment_id))
    payload["case_snapshots"] = snapshots
    plan = QualityPlan(id=uuid4().hex, user_id=user_id, payload=payload,
                       status="planning" if body.planner == "model" else "draft", digest=content_digest(payload))
    db.add(plan)
    db.commit()
    if plan.status == "planning":
        from app.quality.queue import push
        push("planning", plan.id)
    return plan


def approve(db, plan, user_id, expected_digest):
    require_capability(db, user_id, "qa.approve")
    require_execution(db, user_id, plan.payload["kind"])
    db.refresh(plan, with_for_update=True)
    if plan.status != "draft" or expected_digest != plan.digest or content_digest(plan.payload) != plan.digest:
        raise HTTPException(409, "计划尚未就绪或内容已改变，请刷新后重新批准")
    if plan.payload["target_revision"] != fingerprint():
        raise HTTPException(409, "目标代码已变化，请重新生成计划")
    plan.status = "approved"
    plan.approved_by = user_id
    db.commit()


def validate_approval(db, plan):
    from app.quality.case_versions import validate_snapshots
    validate_snapshots(db, plan.payload.get("case_snapshots", []))
    if plan.payload["environment_id"] not in {row["id"] for row in environments()}:
        raise HTTPException(409, "测试环境已停用")
    if plan.status != "approved" or content_digest(plan.payload) != plan.digest:
        raise HTTPException(409, "计划未经有效批准")
    require_capability(db, plan.approved_by, "qa.approve")
    if plan.payload["target_revision"] != fingerprint() or plan.payload["catalog_version"] != CATALOG_VERSION:
        raise HTTPException(409, "代码或用例版本已变化，旧批准失效")


def create_run(db, plan, user_id, request_key):
    require_execution(db, user_id, plan.payload["kind"])
    existing = db.scalar(select(QualityRun).where(QualityRun.user_id == user_id, QualityRun.request_key == request_key))
    if existing:
        if existing.plan_id != plan.id:
            raise HTTPException(409, "幂等键已用于其他计划")
        return existing
    validate_approval(db, plan)
    run = QualityRun(id=uuid4().hex, plan_id=plan.id, user_id=user_id, request_key=request_key,
                     kind=plan.payload["kind"], mode=plan.payload["mode"], status="queued", summary={})
    from sqlalchemy.exc import IntegrityError
    try:
        db.add(run)
        db.flush()
        for case_id in plan.payload["case_ids"]:
            db.add(QualityResult(run_id=run.id, case_id=case_id, kind=next(row["kind"] for row in plan.payload["case_snapshots"] if row["id"] == case_id)))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(QualityRun).where(QualityRun.user_id == user_id, QualityRun.request_key == request_key))
        if not existing or existing.plan_id != plan.id:
            raise HTTPException(409, "任务创建冲突")
        return existing
    from app.quality.queue import push
    push(run.kind, run.id)
    return run


def summarize(results):
    grouped = {}
    for kind in ("assistant", "functional"):
        selected = [row for row in results if row.kind == kind]
        if not selected:
            continue
        counts = Counter(row.status for row in selected)
        eligible = counts.get("passed", 0) == len(selected) and all(row.evidence.get("cleanup_ok") for row in selected)
        grouped[kind] = {"planned": len(selected), "counts": dict(counts), "eligible": eligible}
    return {"groups": grouped, "decision": "eligible" if grouped and all(group["eligible"] for group in grouped.values()) else "not_eligible"}


def plan_out(plan):
    return {"id": plan.id, "status": plan.status, "digest": plan.digest, "payload": plan.payload,
            "approved_by": plan.approved_by, "created_at": plan.created_at, "evidence": plan.evidence}


def run_out(db, run):
    results = db.scalars(select(QualityResult).where(QualityResult.run_id == run.id).order_by(QualityResult.id)).all()
    plan = db.get(QualityPlan, run.plan_id)
    return {"id": run.id, "plan_id": run.plan_id, "kind": run.kind, "mode": run.mode, "status": run.status,
            "cancel_requested": run.cancel_requested, "created_at": run.created_at,
            "started_at": run.started_at, "finished_at": run.finished_at, "summary": run.summary,
            "target": {key: plan.payload.get(key) for key in ("target_revision", "environment_id", "fixture_version", "catalog_version", "case_snapshots")},
            "results": [{"id": row.case_id, "kind": row.kind, "status": row.status, "evidence": row.evidence} for row in results]}
