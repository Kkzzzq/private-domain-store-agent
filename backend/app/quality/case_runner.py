import argparse
import contextlib
import io
import json
import os
import logging
from pathlib import Path
from time import perf_counter

from app.quality.catalog import ASSISTANT_CASES, FUNCTIONAL_TESTS
from app.quality.sandbox import Evidence, ModelBudget, configure_environment, safe


def execute(spec):
    configure_environment()
    from app.quality.browser import BROWSER_CASES
    if spec["case_id"] in BROWSER_CASES and not os.environ.get("QA_NATIVE_DATABASE_URL"):
        os.environ["DATABASE_URL"] = "sqlite:///" + (Path(os.environ["QA_CHILD_WORKSPACE"]) / "browser.db").as_posix()
    from app.quality.native import install_namespace
    install_namespace()
    evidence = Evidence()
    warnings = []
    class DiagnosticHandler(logging.Handler):
        def emit(self, record):
            if len(warnings) < 20:
                warnings.append(safe(record.getMessage()))
    from app.core.logging import logger
    handler = DiagnosticHandler(level=logging.WARNING)
    logger.addHandler(handler)
    restore = evidence.install()
    started = perf_counter()
    output = {"status": "blocked", "requests": evidence.requests, "assertions": evidence.assertions,
              "environment": {"database": "sqlite", "redis": "memory", "fixture": "seed-isolated-v1"},
              "mode": spec["mode"], "cleanup_ok": False}
    budget = ModelBudget(spec["max_calls"], spec["max_tokens"])
    if os.environ.get("QA_NATIVE_PREFIX"):
        output["environment"] = {"database": "mysql", "redis": "redis", "fixture": "seed-isolated-v1", "isolation": "unique_database_and_redis_prefix"}
    restore_model = None
    try:
        if os.environ.get("QA_NATIVE_PREFIX"):
            from app.db.session import engine
            from app.db.redis_client import get_redis
            from sqlalchemy import text
            with engine.connect() as connection:
                database = connection.scalar(text("SELECT DATABASE()"))
            evidence.check("真实MySQL使用独立测试库", engine.dialect.name == "mysql" and database.startswith("qa_"), None, {"driver": engine.dialect.name, "database": database})
            cache = get_redis()
            cache.set_json("quality-dependency-proof", {"native": True}, ex=60)
            evidence.check("真实Redis键仅落在测试命名空间", not cache.using_memory and cache._client.raw.get(os.environ["QA_NATIVE_PREFIX"] + "quality-dependency-proof") == '{"native": true}')
        if spec["case_id"] in BROWSER_CASES:
            from app.quality.browser import execute_browser
            output.update(execute_browser(spec["case_id"], evidence))
        elif spec["case_id"] in FUNCTIONAL_TESTS:
            import pytest
            reports = []
            class Plugin:
                def pytest_runtest_logreport(self, report):
                    reports.append({"node": report.nodeid, "stage": report.when, "outcome": report.outcome,
                                    "failure": safe(str(report.longrepr)) if report.failed else None})
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                code = pytest.main(["tests/" + FUNCTIONAL_TESTS[spec["case_id"]], "-q", "--disable-warnings", "-p", "no:cacheprovider", "--basetemp", os.environ["QA_CHILD_WORKSPACE"] + "/pytest"], plugins=[Plugin()])
            evidence.check("固定回归确实收集并执行且未跳过", code == 0 and any(row["stage"] == "call" and row["outcome"] == "passed" for row in reports) and all(row["outcome"] == "passed" for row in reports), "执行并通过", reports)
            output["suite"] = {"adapter": "registered_pytest", "node": FUNCTIONAL_TESTS[spec["case_id"]], "reports": reports}
        elif spec["case_id"] in ASSISTANT_CASES or any(row["id"] == spec["case_id"] and row.get("adapter") == "declarative_assistant" for row in spec.get("case_snapshots", [])):
            if spec["mode"] == "live":
                restore_model = budget.install()
            custom = next((row for row in spec.get("case_snapshots", []) if row["id"] == spec["case_id"] and row.get("adapter") == "declarative_assistant"), None)
            if custom:
                if spec["mode"] != "live":
                    raise RuntimeError("自定义助手场景只能按真实模型模式执行")
                from app.quality.case_versions import execute_definition
                output.update(execute_definition(custom["definition"], evidence))
            else:
                from app.quality.scenarios import assistant_case
                output.update(assistant_case(spec["case_id"], evidence, spec["mode"]))
        else:
            raise RuntimeError("未登记的测试用例")
        output["status"] = "passed"
    except AssertionError as exc:
        output.update(status="failed", error=safe(str(exc)))
    except Exception as exc:
        output.update(status="blocked", error=safe(type(exc).__name__ + ": " + str(exc)))
    finally:
        if getattr(evidence, "artifacts", None):
            output["artifacts"] = evidence.artifacts
        logger.removeHandler(handler)
        output["diagnostics"] = warnings
        restore()
        if restore_model:
            restore_model()
    output.update(duration_ms=round((perf_counter() - started) * 1000), budget=budget.output())
    if budget.exhausted:
        output.update(status="blocked", error="模型预算不足：下一次请求的保守预留超过剩余预算，已在发送前停止；请增加预算后新建运行。")
    return safe(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    spec = json.loads(Path(args.request).read_text(encoding="utf-8"))
    result = execute(spec)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
