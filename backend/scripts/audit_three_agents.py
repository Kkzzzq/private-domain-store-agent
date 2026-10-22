"""Read-only regression probes for the previously reproduced Agent capability gaps."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.quality.agent_evaluation import calibrate_tester, program_checks
from app.quality.heldout import score_results, write_expectations
from app.quality.service import PlanIn
from app.services.product_search import search_rows


def main():
    evidence = {"cleanup_ok": True, "assertions": [{"name": "precondition", "passed": True}],
                "requests": [{"path": "/chat", "input": {"message": "查询商品"},
                              "output": {"answer": "商品存在", "tools": [{"tool": "search_products"}]}}]}
    report = {"results": [{"id": "A02", "kind": "assistant", "status": "blocked", "evidence": evidence}],
              "target": {"case_ids": ["A02"], "case_snapshots": [{"id": "A02", "kind": "assistant"}]}}
    program = program_checks(report, "business")
    findings = {"blocked_source_program_decision": program["decision"]}
    with TemporaryDirectory(prefix="agent-audit-") as directory:
        path = Path(directory) / "answers.json"
        write_expectations({"H-cart-illegal-quantity": True}, path)
        heldout = score_results([{"id": "F11", "status": "failed", "evidence": {
            "assertions": [{"name": "固定回归确实收集并执行且未跳过", "passed": True},
                           {"name": "购物车状态正确", "passed": False}]}}], path)
        findings["failed_source_heldout_passed"] = heldout["passed"]
        findings["heldout_unavailable_entries"] = sum(row["status"] == "expectation_unavailable" for row in heldout["entries"])
    try:
        PlanIn(goal="审查功能执行模型开关", kind="functional", case_ids=["F01"],
               environment_id="isolated-local", functional_driver=False)
        findings["formal_functional_driver_false_accepted"] = True
    except ValueError:
        findings["formal_functional_driver_false_accepted"] = False
    callbacks = []

    def executor(spec, cancelled):
        callbacks.append(cancelled())
        return {"status": "passed", "cleanup_ok": True, "functional_agent": {"synthetic_probe": True}, "assertions": []}

    revoked = lambda: bool(callbacks)
    try:
        calibrate_tester(executor, revoked)
        findings['benchmark_stopped_on_revocation'] = False
    except ValueError:
        findings['benchmark_stopped_on_revocation'] = True
    findings["benchmark_cancel_callbacks"] = callbacks
    rows = [{"id": 1, "name": "马克杯", "category": "餐具", "description": "喝水用", "tags": [],
             "skus": [{"id": 11, "spec": "白色", "parameters": {}}]},
            {"id": 2, "name": "陶瓷饮水器", "category": "餐具", "description": "喝水用", "tags": [],
             "skus": [{"id": 21, "spec": "白色", "parameters": {}}]}]
    with patch("app.services.product_search.semantic_matches", return_value={(2, 21): 0.1}) as semantic:
        selected = search_rows("马克杯", rows, None, None)
        findings["literal_hit_skips_semantic_recall"] = len(selected) == 1 and semantic.call_count == 0
    assert findings["blocked_source_program_decision"] == "failed"
    assert findings["failed_source_heldout_passed"] is False
    assert findings["formal_functional_driver_false_accepted"] is False
    assert len(callbacks) == 1 and findings['benchmark_stopped_on_revocation']
    assert findings["literal_hit_skips_semantic_recall"] is False
    print(json.dumps({"scope": "synthetic deterministic probes; no model/DB/network calls", "findings": findings}, ensure_ascii=False))


if __name__ == "__main__":
    main()
