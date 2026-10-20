import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.quality import QualityPlan, QualityResult, QualityRun
from app.models.tables import utcnow
from app.quality import queue, service
from app.quality.sandbox import safe


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def subprocess_job(spec, cancelled, planner=False):
    root = settings.backend_root / "data" / "quality-workspaces"
    root.mkdir(parents=True, exist_ok=True)
    output = {"status": "blocked", "error": "子进程未产出有效证据", "cleanup_ok": False}
    native = None
    try:
        with tempfile.TemporaryDirectory(prefix="qa-", dir=root) as directory:
            workspace = Path(directory)
            request = workspace / "request.json"
            result = workspace / "result.json"
            request.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            environment = dict(os.environ, QA_CHILD_RUN=uuid4().hex, QA_CHILD_WORKSPACE=directory,
                               PYTHONIOENCODING="utf-8", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
            if spec.get("environment_id") == "native-local" and not planner:
                from app.quality.native import NativeWorkspace
                native = NativeWorkspace()
                environment.update(native.prepare())
            arguments = [sys.executable, "-m", "app.quality.planner" if planner else "app.quality.case_runner",
                         "--request", str(request), "--output", str(result)]
            produced = False
            with (workspace / "process.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(arguments, cwd=settings.backend_root, env=environment, stdout=log, stderr=log,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                           start_new_session=os.name != "nt")
                deadline = time.monotonic() + min(90, spec.get("timeout_seconds", 90))
                try:
                    while process.poll() is None:
                        if cancelled():
                            output = {"status": "cancelled", "error": "已取消或质量授权已撤销"}
                            break
                        if time.monotonic() > deadline:
                            output = {"status": "blocked", "error": "隔离步骤超时，已停止子进程"}
                            break
                        time.sleep(0.3)
                    else:
                        if process.returncode == 0 and result.exists() and result.stat().st_size < 3_000_000:
                            output = json.loads(result.read_text(encoding="utf-8"))
                            produced = True
                finally:
                    stop_process(process)
            if not produced:
                may_call_model = planner or spec.get("mode") == "live"
                output["budget"] = {"calls": max(0, spec.get("max_calls", 0)) if may_call_model else 0, "tokens": max(0, spec.get("max_tokens", 0)) if may_call_model else 0,
                                    "estimated": may_call_model, "uncertain": may_call_model, "scope": "子进程中断；模型模式按剩余额度保守占用，非实际计费；规则模式无模型调用"}
        output["cleanup_ok"] = True
    except Exception as exc:
        output = {"status": "blocked", "error": safe(type(exc).__name__ + ": " + str(exc)), "cleanup_ok": False}
    finally:
        if native:
            try:
                native.close()
            except Exception as exc:
                output.update(status="blocked", error=safe(str(exc)), cleanup_ok=False)
    return output


def run_one(run_id, session_factory=SessionLocal, executor=subprocess_job):
    with session_factory() as db:
        run = db.get(QualityRun, run_id)
        if not run or run.status != "queued":
            return False
        kinds = ("assistant", "functional") if run.kind == "joint" else (run.kind,)
        locks = []
        try:
            for kind in kinds:
                token = queue.acquire(kind)
                if not token:
                    return False
                locks.append((kind, token))
            claimed = db.execute(update(QualityRun).where(QualityRun.id == run.id, QualityRun.status == "queued").values(status="running", started_at=utcnow(), lease_until=utcnow() + timedelta(seconds=110)))
            db.commit()
            if claimed.rowcount != 1:
                return False
            db.refresh(run)
            plan = db.get(QualityPlan, run.plan_id)
            results = db.scalars(select(QualityResult).where(QualityResult.run_id == run.id).order_by(QualityResult.kind.desc(), QualityResult.id)).all()
            started = time.monotonic()
            used_calls = plan.evidence.get("budget", {}).get("calls", 0)
            used_tokens = plan.evidence.get("budget", {}).get("tokens", 0)
            last_heartbeat = time.monotonic()
            def cancelled():
                nonlocal last_heartbeat
                db.commit()
                db.refresh(run)
                if run.status != "running":
                    return True
                if time.monotonic() - last_heartbeat > 10:
                    if not all(queue.renew(kind, token) for kind, token in locks):
                        return True
                    run.lease_until = utcnow() + timedelta(seconds=110)
                    db.commit()
                    last_heartbeat = time.monotonic()
                caps = service.capabilities(db, run.user_id)
                approved = "qa.approve" in service.capabilities(db, plan.approved_by)
                return run.cancel_requested or not approved or "qa.view" not in caps or any(f"qa.{kind}.run" not in caps for kind in kinds) or time.monotonic() - started > plan.payload["timeout_seconds"]
            try:
                service.validate_approval(db, plan)
                service.require_execution(db, run.user_id, run.kind)
                for result in results:
                    if cancelled():
                        break
                    db.refresh(plan)
                    service.validate_approval(db, plan)
                    result.status = "running"
                    run.lease_until = utcnow() + timedelta(seconds=110)
                    db.commit()
                    spec = {**plan.payload, "case_id": result.case_id, "mode": run.mode if result.kind == "assistant" else "rules",
                            "max_calls": plan.payload["max_calls"] - used_calls, "max_tokens": plan.payload["max_tokens"] - used_tokens,
                            "timeout_seconds": min(90, max(1, int(plan.payload["timeout_seconds"] - (time.monotonic() - started))))}
                    if result.kind == "assistant" and run.mode == "live" and (spec["max_calls"] <= 0 or spec["max_tokens"] <= 0):
                        output = {"status": "blocked", "error": "父任务共享预算已耗尽", "cleanup_ok": True}
                    else:
                        output = executor(spec, cancelled)
                    result.status = output.get("status", "blocked") if output.get("status") in ("passed", "failed", "blocked", "cancelled") else "blocked"
                    if result.status == "passed" and (not output.get("assertions") or not all(row.get("passed") for row in output["assertions"]) or not output.get("cleanup_ok")):
                        result.status = "blocked"
                        output["error"] = "缺少断言或隔离清理未确认"
                    if result.status == "passed" and result.kind == "assistant":
                        chats = [row for row in output.get("requests", []) if row.get("path", "").endswith("/chat") and row.get("status") == 200]
                        expected_modes = {"llm"} if run.mode == "live" else {"fallback", "direct"}
                        if not chats or any(row.get("output", {}).get("mode") not in expected_modes for row in chats):
                            result.status = "blocked"
                            output["error"] = "缺少被测业务Agent对话或实际执行模式不符"
                    if result.status == "passed" and plan.payload["environment_id"] == "native-local":
                        if output.get("environment", {}).get("database") != "mysql" or output.get("environment", {}).get("redis") != "redis":
                            result.status = "blocked"
                            output["error"] = "原生依赖档缺少真实MySQL/Redis执行证明"
                    if result.status == "passed" and result.kind == "functional":
                        reports = output.get("suite", {}).get("reports", [])
                        if not reports or not any(row.get("stage") == "call" and row.get("outcome") == "passed" for row in reports) or any(row.get("outcome") != "passed" for row in reports):
                            result.status = "blocked"
                            output["error"] = "固定测试未执行或存在跳过/失败"
                    result.evidence = output
                    used_calls += output.get("budget", {}).get("calls", 0)
                    used_tokens += output.get("budget", {}).get("tokens", 0)
                    db.commit()
            except Exception as exc:
                db.rollback()
                run.summary = {"error": safe(type(exc).__name__ + ": " + str(exc))}
            db.refresh(run)
            if run.status != "running":
                return False
            for result in results:
                if result.status in ("queued", "running"):
                    result.status = "cancelled" if run.cancel_requested else "blocked"
                    result.evidence = {"error": "任务中止、授权变化或前置条件失效，未计入通过", "cleanup_ok": True}
            previous_error = run.summary.get("error")
            run.summary = {**service.summarize(results), "budget": {"calls": used_calls, "tokens": used_tokens},
                           "error": previous_error, "execution": plan.payload["environment"]["description"]}
            run.status = "cancelled" if run.cancel_requested else "failed" if any(row.status == "failed" for row in results) else "blocked" if any(row.status == "blocked" for row in results) else "completed"
            run.finished_at = utcnow()
            run.lease_until = None
            db.commit()
            return True
        finally:
            for kind, token in locks:
                queue.release(kind, token)


def plan_one(plan_id, session_factory=SessionLocal, executor=subprocess_job):
    token = queue.acquire("planning")
    if not token:
        return False
    try:
        with session_factory() as db:
            plan = db.get(QualityPlan, plan_id)
            if not plan or plan.status != "planning":
                return False
            claimed = db.execute(update(QualityPlan).where(QualityPlan.id == plan_id, QualityPlan.status == "planning").values(status="planning_running", started_at=utcnow()))
            db.commit()
            if claimed.rowcount != 1:
                return False
            db.refresh(plan)
            try:
                service.require_execution(db, plan.user_id, plan.payload["kind"])
                def cancelled_plan():
                    db.commit()
                    caps = service.capabilities(db, plan.user_id)
                    kinds = ("assistant", "functional") if plan.payload["kind"] == "joint" else (plan.payload["kind"],)
                    return "qa.view" not in caps or any(f"qa.{kind}.run" not in caps for kind in kinds)
                output = executor(plan.payload, cancelled_plan, planner=True)
                if output.get("status") == "draft" and output.get("cleanup_ok"):
                    payload = {**plan.payload, "case_ids": output["proposal"]["case_ids"]}
                    service.PlanIn.model_validate({key: payload[key] for key in service.PlanIn.model_fields})
                    if not set(payload["case_ids"]).issubset(plan.payload["case_ids"]):
                        raise ValueError("规划越过授权用例集合")
                    plan.payload = payload
                    plan.digest = service.content_digest(payload)
                    plan.status = "draft"
                else:
                    plan.status = "blocked"
                plan.evidence = output
            except Exception as exc:
                plan.status = "blocked"
                plan.evidence = {"error": safe(type(exc).__name__ + ": " + str(exc))}
            db.commit()
            return True
    finally:
        queue.release("planning", token)


_last_retention = 0.0


def tick():
    global _last_retention
    with SessionLocal() as db:
        for plan in db.scalars(select(QualityPlan).where(QualityPlan.status == "planning_running", QualityPlan.started_at < utcnow() - timedelta(seconds=110))):
            plan.status = "blocked"
            plan.evidence = {"error": "规划worker中断，未自动重放付费调用，请新建计划"}
        expired = db.scalars(select(QualityRun).where(QualityRun.status == "running", QualityRun.lease_until < utcnow())).all()
        for run in expired:
            run.status = "blocked"
            run.finished_at = utcnow()
            run.summary = {"decision": "not_eligible", "error": "worker租约过期，未自动重放写步骤；请核对后新建运行"}
            for result in db.scalars(select(QualityResult).where(QualityResult.run_id == run.id, QualityResult.status.in_(["queued", "running"]))):
                result.status = "blocked"
                result.evidence = {"error": "worker中断，执行结果不确定"}
        db.commit()
        # 报告保留策略：每小时最多自动清理一次（默认删 7 天前的已结束运行及其孤立截图）。
        if time.monotonic() - _last_retention > 3600:
            _last_retention = time.monotonic()
            from app.quality.reporting import retention_auto
            from app.core.logging import logger
            try:
                retention_auto(db)
            except Exception:
                logger.exception("自动清理历史报告失败，保留数据待下轮重试")
        waiting_plan = db.scalar(select(QualityPlan.id).where(QualityPlan.status == "planning").order_by(QualityPlan.created_at))
        waiting_run = db.scalar(select(QualityRun.id).where(QualityRun.status == "queued").order_by(QualityRun.created_at))
    plan_id = queue.pop("planning") or waiting_plan
    if plan_id:
        return plan_one(plan_id)
    for kind in ("assistant", "functional", "joint"):
        run_id = queue.pop(kind)
        if run_id and run_one(run_id):
            return True
    return run_one(waiting_run) if waiting_run else False


def main():
    parser = argparse.ArgumentParser(description="OP隔离质量worker；只执行受限合成环境任务")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    from app.main import init_db
    init_db()
    while True:
        try:
            tick()
        except Exception:
            if args.once:
                raise
            from app.core.logging import logger
            logger.exception("质量worker步骤失败，持久状态待下轮核查")
        if args.once:
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
