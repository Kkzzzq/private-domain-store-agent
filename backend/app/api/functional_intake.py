"""自由需求受理接口：判断需求能否由当前环境已登记的功能工具实现，并给出可审批的功能测试计划。

判断在隔离子进程中由独立测试模型完成；本接口不执行任何业务写入，只读真实功能目录。
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.quality import quality_user
from app.core.deps import get_db
from app.db.redis_client import get_redis
from app.quality import queue, service
from app.quality.catalog import case_by_id, environments
from app.quality.case_versions import all_cases
from app.quality.feature_catalog import catalog

router = APIRouter(prefix="/op/qa/functional-intake", tags=["OP functional intake"])
HISTORY_KEY = "qa:functional-intake:{user}"
RATE_KEY = "qa:functional-intake-rate:{user}"


class IntakeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement: str = Field(min_length=4, max_length=600)
    environment_id: str = Field(default="isolated-local", pattern="^(isolated-local|native-local|real-nanzhi)$")


def plan_payload(db, requirement, environment_id, verdict, judged_version):
    """由服务端拼装计划，只接受目录中已登记的用例；模型不能直接决定环境、预算或绕过审批。

    注意：计划绑定的是「所选用例子集」的功能目录版本（bind_plan 用 case_snapshots 计算），
    与受理判断使用的全量目录版本可能不同，因此这里重新计算并把两个版本都写清楚。
    """
    from app.quality.case_versions import resolve
    case_ids = []
    for case_id in verdict.get("case_ids", []):
        row = case_by_id(case_id)
        if row and row["kind"] == "functional" and row["state"] == "active":
            case_ids.append(case_id)
    if not case_ids:
        return None, None
    selected = [resolve(db, case_id) for case_id in case_ids]
    bound = catalog([row for row in selected if row])
    diagnostic = environment_id == "real-nanzhi"
    payload = {"kind": "functional",
               "goal": f"{requirement.strip()}（执行绑定功能目录 {bound['version'][:12]}；受理依据全量目录 {judged_version[:12]}；环境 {environment_id}）",
               "case_ids": case_ids, "environment_id": environment_id, "mode": "rules",
               "planner": "fixed" if diagnostic else "model", "diagnostic": diagnostic,
               "functional_driver": not diagnostic,
               "max_calls": 30, "max_tokens": 60000, "timeout_seconds": 1200}
    return payload, bound["version"]


@router.get("")
def history(user=Depends(quality_user)):
    return get_redis().get_json(HISTORY_KEY.format(user=user.id)) or []


@router.post("", status_code=201)
def intake(body: IntakeIn, user=Depends(quality_user), db=Depends(get_db)):
    from app.core.config import settings
    service.require_execution(db, user.id, "functional")
    if body.environment_id not in {row["id"] for row in environments()}:
        raise HTTPException(422, "该测试环境未授权启用")
    if not settings.qa_chat_model or not settings.qa_chat_api_key_file:
        raise HTTPException(503, "缺少独立测试模型配置，无法判断需求可实现性")
    if get_redis().increment(RATE_KEY.format(user=user.id), 600) > 10:
        raise HTTPException(429, "需求受理过于频繁，请稍后重试")
    token = queue.acquire("functional-intake")
    if not token:
        raise HTTPException(409, "已有需求受理在执行，请稍后重试")
    try:
        snapshot = catalog(all_cases(db))
        from app.quality.worker import subprocess_job
        from app.quality.sandbox import safe

        def cancelled():
            db.rollback()
            return not {"qa.view", "qa.functional.run"}.issubset(service.capabilities(db, user.id))

        output = subprocess_job({"intake_job": True, "case_id": "__functional_intake__",
                                 "requirement": body.requirement, "environment_id": body.environment_id,
                                 "feature_catalog": snapshot, "max_calls": 3, "max_tokens": 20000,
                                 "timeout_seconds": 90}, cancelled)
        verdict = output.get("verdict") or {}
        feasible = bool(verdict.get("feasible"))
        plan, plan_version = plan_payload(db, body.requirement, body.environment_id, verdict, snapshot["version"]) if feasible else (None, None)
        if output.get("status") == "completed" and feasible and not plan:
            output = {**output, "status": "blocked", "error": "需求判为可实现，但没有可提交的已登记用例"}
        if output.get("status") != "completed" and not output.get("error"):
            output = {**output, "status": "blocked", "error": "受理未产出判断依据"}
        record = {"id": uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(),
                  "requirement": safe(body.requirement), "environment_id": body.environment_id,
                  "catalog_version": snapshot["version"], "plan_catalog_version": plan_version,
                  "status": output.get("status"), "error": output.get("error"),
                  "verdict": safe(verdict), "plan": plan,
                  "evidence": output}
        cache = get_redis()
        key = HISTORY_KEY.format(user=user.id)
        cache.set_json(key, [record, *(cache.get_json(key) or [])][:10], ex=604800)
        return record
    finally:
        queue.release("functional-intake", token)