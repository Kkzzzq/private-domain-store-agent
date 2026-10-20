from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.op_api import require_operator
from app.core.deps import get_db
from app.models.quality import QualityPlan, QualityRun, QualityCaseVersion
from app.quality.case_versions import CaseIn
from app.quality import service
from app.quality.catalog import CATALOG_VERSION, environments, cases

router = APIRouter(prefix="/op/qa", tags=["OP quality"])


def quality_user(user=Depends(require_operator), db=Depends(get_db)):
    service.require_capability(db, user.id, "qa.view")
    return user


def get_record(db, model, record_id):
    record = db.get(model, record_id)
    if not record:
        raise HTTPException(404, "测试记录不存在")
    return record


@router.get("/capabilities")
def capabilities(user=Depends(quality_user), db=Depends(get_db)):
    return {"capabilities": sorted(service.capabilities(db, user.id)), "environments": environments(),
            "catalog_version": CATALOG_VERSION, "case_counts": {kind: sum(row["kind"] == kind and row["state"] == "active" for row in cases()) for kind in ("assistant", "functional")},
            "limits": {"max_cases": 20, "max_calls": 50, "max_tokens": 60000},
            "limitations": ["所有执行档仅合成数据，不对真实店铺写测试", "接入数量与运行通过数量分开", "浏览器适配需requirements-e2e及浏览器运行时，缺依赖记阻塞"]}


@router.get("/cases")
def list_cases(user=Depends(quality_user), db=Depends(get_db)):
    from app.quality.case_versions import all_cases
    return all_cases(db)


@router.post("/plans", status_code=201)
def create_plan(body: service.PlanIn, user=Depends(quality_user), db=Depends(get_db)):
    return service.plan_out(service.new_plan(db, user.id, body))


@router.get("/plans")
def list_plans(user=Depends(quality_user), db=Depends(get_db)):
    return [service.plan_out(row) for row in db.scalars(select(QualityPlan).order_by(QualityPlan.created_at.desc()).limit(30))]


@router.get("/plans/{plan_id}")
def get_plan(plan_id: str, user=Depends(quality_user), db=Depends(get_db)):
    return service.plan_out(get_record(db, QualityPlan, plan_id))


class ApprovalIn(BaseModel):
    digest: str = Field(min_length=64, max_length=64)


@router.post("/plans/{plan_id}/approve")
def approve_plan(plan_id: str, body: ApprovalIn, user=Depends(quality_user), db=Depends(get_db)):
    plan = get_record(db, QualityPlan, plan_id)
    service.approve(db, plan, user.id, body.digest)
    return service.plan_out(plan)


class RunIn(BaseModel):
    plan_id: str = Field(min_length=32, max_length=32)
    request_key: str = Field(min_length=8, max_length=80)


@router.post("/runs", status_code=201)
def create_run(body: RunIn, user=Depends(quality_user), db=Depends(get_db)):
    plan = get_record(db, QualityPlan, body.plan_id)
    return service.run_out(db, service.create_run(db, plan, user.id, body.request_key))


@router.get("/runs")
def list_runs(user=Depends(quality_user), db=Depends(get_db)):
    return [service.run_out(db, row) for row in db.scalars(select(QualityRun).order_by(QualityRun.created_at.desc()).limit(30))]


@router.get("/runs/{run_id}")
@router.get("/runs/{run_id}/report")
def get_run(run_id: str, user=Depends(quality_user), db=Depends(get_db)):
    return service.run_out(db, get_record(db, QualityRun, run_id))


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, user=Depends(quality_user), db=Depends(get_db)):
    run = get_record(db, QualityRun, run_id)
    service.require_execution(db, user.id, run.kind)
    if run.status in ("queued", "running"):
        run.cancel_requested = True
        db.commit()
    return service.run_out(db, run)


@router.post("/runs/{run_id}/rerun", status_code=201)
def rerun(run_id: str, user=Depends(quality_user), db=Depends(get_db)):
    previous = get_record(db, QualityRun, run_id)
    return service.run_out(db, service.create_run(db, get_record(db, QualityPlan, previous.plan_id), user.id, uuid4().hex))


@router.get("/compare")
def compare_runs(baseline: str, candidate: str, user=Depends(quality_user), db=Depends(get_db)):
    from app.quality.reporting import compare
    return compare(db, get_record(db, QualityRun, baseline), get_record(db, QualityRun, candidate))


@router.get("/runs/{run_id}/artifacts/{artifact_id}")
def artifact(run_id: str, artifact_id: str, user=Depends(quality_user), db=Depends(get_db)):
    from app.quality.reporting import owned_artifact
    return FileResponse(owned_artifact(db, run_id, artifact_id), media_type="image/png")


class RetentionIn(BaseModel):
    days: int = Field(default=30, ge=7, le=3650)


class RetentionApplyIn(RetentionIn):
    digest: str = Field(min_length=64, max_length=64)


@router.post("/retention/preview")
def preview_retention(body: RetentionIn, user=Depends(quality_user), db=Depends(get_db)):
    service.require_capability(db, user.id, "qa.approve")
    from app.quality.reporting import retention_preview
    return retention_preview(db, body.days)


@router.post("/retention/apply")
def apply_retention(body: RetentionApplyIn, user=Depends(quality_user), db=Depends(get_db)):
    service.require_capability(db, user.id, "qa.approve")
    from app.quality.reporting import retention_apply
    return retention_apply(db, body.days, body.digest)


def locked_case(db, case_id):
    row = db.scalar(select(QualityCaseVersion).where(QualityCaseVersion.id == case_id).with_for_update())
    if row is None:
        raise HTTPException(404, "用例版本不存在")
    return row


@router.post("/cases", status_code=201)
def create_case(body: CaseIn, user=Depends(quality_user), db=Depends(get_db)):
    service.require_capability(db, user.id, "qa.assistant.run")
    from app.quality.case_versions import create
    return create(db, user.id, body)


@router.patch("/cases/{case_id}")
def edit_case(case_id: str, body: CaseIn, user=Depends(quality_user), db=Depends(get_db)):
    service.require_capability(db, user.id, "qa.assistant.run")
    row = locked_case(db, case_id)
    if row.state != "candidate":
        raise HTTPException(409, "已审核版本不可修改，请创建新版本")
    row.specification = body.model_dump()
    db.commit()
    from app.quality.case_versions import snapshot
    return snapshot(row)


@router.post("/cases/{case_id}/revisions", status_code=201)
def revise_case(case_id: str, body: CaseIn, user=Depends(quality_user), db=Depends(get_db)):
    service.require_capability(db, user.id, "qa.assistant.run")
    from app.quality.case_versions import create
    return create(db, user.id, body, get_record(db, QualityCaseVersion, case_id))


@router.post("/cases/{case_id}/approve")
def approve_case(case_id: str, body: ApprovalIn, user=Depends(quality_user), db=Depends(get_db)):
    service.require_capability(db, user.id, "qa.approve")
    row = locked_case(db, case_id)
    from app.quality.case_versions import snapshot
    if row.state != "candidate" or body.digest != snapshot(row)["revision_digest"]:
        raise HTTPException(409, "用例版本已变化或已审核")
    row.state, row.approved_by = "active", user.id
    db.commit()
    return snapshot(row)


@router.post("/cases/{case_id}/revoke")
def revoke_case(case_id: str, user=Depends(quality_user), db=Depends(get_db)):
    service.require_capability(db, user.id, "qa.approve")
    row = locked_case(db, case_id)
    row.state = "revoked"
    db.commit()
    from app.quality.case_versions import snapshot
    return snapshot(row)
