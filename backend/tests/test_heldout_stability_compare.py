"""不公开评测集、重复执行稳定性与评测跨版本对比。"""
import json
from pathlib import Path

import pytest

from app.quality import heldout, stability
from app.quality.evaluation_compare import compare
from test_quality import operator


def write_answers(tmp_path, entries):
    return heldout.write_expectations(entries, tmp_path / "expectations.json")


def test_public_view_never_exposes_answers_and_missing_file_never_passes(tmp_path):
    answers = {"H-cart-illegal-quantity": True, "H-order-shortage": True, "H-buyer-merchant-denied": True}
    file = write_answers(tmp_path, answers)
    view = heldout.public_view(file)
    assert view["available"] and view["sealed_digest"]
    assert all(row["status"] == "sealed" for row in view["entries"])
    assert all(row["expect_hash"] for row in view["entries"])
    blob = json.dumps(view, ensure_ascii=False)
    assert all("expect" not in row for row in view["entries"])        # 公开视图不含期望值字段
    assert '"expect":' not in blob
    assert all(str(value) not in blob for value in answers.values() if not isinstance(value, bool))

    missing = heldout.public_view(tmp_path / "absent.json")
    assert not missing["available"] and missing["sealed_digest"] is None
    assert all(row["status"] == "expectation_unavailable" for row in missing["entries"])
    scored = heldout.score_results([{"id": "F11", "evidence": {"assertions": [{"name": "固定回归确实收集并执行且未跳过", "passed": True}]}}],
                                   tmp_path / "absent.json")
    assert scored["passed"] is False and all(row["status"] == "expectation_unavailable" for row in scored["entries"])
    assert "never counts as pass" in scored["note"]


def test_tampered_answers_are_rejected_and_reveal_reports_digest(tmp_path):
    file = write_answers(tmp_path, {"H-order-shortage": True})
    payload = json.loads(Path(file).read_text(encoding="utf-8"))
    payload["entries"][0]["expect"] = False                          # 改答案不改摘要
    Path(file).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="答案与摘要不一致"):
        heldout.load_expectations(file)
    good = write_answers(tmp_path, {"H-buyer-merchant-denied": True})
    answer = heldout.reveal("H-buyer-merchant-denied", good)
    assert answer["status"] == "revealed" and answer["expect"] is True and answer["expect_hash"]
    assert heldout.reveal("H-cart-illegal-quantity", good)["status"] == "expectation_unavailable"
    with pytest.raises(KeyError):
        heldout.reveal("not-an-entry", good)


def test_scoring_uses_generic_probe_and_marks_not_observed(tmp_path):
    file = write_answers(tmp_path, {"H-cart-illegal-quantity": True, "H-order-shortage": False})
    results = [{"id": "F11", "evidence": {"assertions": [{"name": "固定回归确实收集并执行且未跳过", "passed": True}]}}]
    scored = heldout.score_results(results, file)
    entries = {row["id"]: row for row in scored["entries"]}
    assert entries["H-cart-illegal-quantity"]["status"] == "matched" and entries["H-cart-illegal-quantity"]["passed"]
    assert entries["H-order-shortage"]["status"] == "not_observed" and not entries["H-order-shortage"]["passed"]
    assert entries["H-buyer-merchant-denied"]["status"] == "expectation_unavailable"
    assert scored["passed"] is False                                  # 有未观察条目就不能算整份通过
    assert entries["H-cart-illegal-quantity"]["observed_digest"]      # 只回摘要，不回观察值


def test_stability_summary_distinguishes_stable_from_flaky():
    def run(ident, statuses):
        return {"id": ident, "created_at": ident,
                "results": [{"id": case_id, "kind": "functional", "status": status} for case_id, status in statuses.items()]}

    stable = stability.summarize_runs([run("a", {"F11": "passed"}), run("b", {"F11": "passed"})], plan_id="p")
    assert stable["verdict"] == "stable_pass" and stable["attempts"] == 2
    assert stable["cases"][0]["consistent"] is True
    flaky = stability.summarize_runs([run("a", {"F11": "passed"}), run("b", {"F11": "failed"})], plan_id="p")
    assert flaky["verdict"] == "flaky" and "摆动" in flaky["note"]
    defect = stability.summarize_runs([run("a", {"F17": "failed"}), run("b", {"F17": "failed"})], plan_id="p")
    assert defect["verdict"] == "stable_fail" and "一致的产品缺陷" in defect["note"]
    once = stability.summarize_runs([run("a", {"F11": "passed"})], plan_id="p")
    assert once["verdict"] == "insufficient" and "证据不足" in once["note"]
    assert stability.summarize_runs([], plan_id="p")["verdict"] == "insufficient"
    assert stability.summarize_runs([run("a", {"F11": "blocked"}), run("b", {"F11": "blocked"})])["verdict"] == "blocked"


def test_evaluation_comparison_declares_comparability():
    def evaluation(ident, target, rubric, decision, checks, dims, source="run-1"):
        return {"id": ident, "target": target, "version": 1, "source_run": source,
                "snapshot": {"rubric": rubric},
                "program": {"decision": decision, "checks": [{"name": name, "status": status} for name, status in checks.items()]},
                "model_score": {"dimensions": [{"dimension": key, "score": value} for key, value in dims.items()]}, "reviews": []}

    base = evaluation("a", "functional", "v1", "incomplete", {"计划执行范围完整": "passed", "已知缺陷检出/正常版本误报": "not_observed"}, {"defect_detection": None, "cleanup": 4})
    cand = evaluation("b", "functional", "v1", "passed", {"计划执行范围完整": "passed", "已知缺陷检出/正常版本误报": "passed"}, {"defect_detection": 4, "cleanup": 4}, source="run-2")
    result = compare(base, cand)
    assert not result["comparable"] and any("来源运行不同" in reason for reason in result["incompatible_reasons"])
    transitions = {row["name"]: row for row in result["program"]}
    assert transitions["已知缺陷检出/正常版本误报"]["changed"] and "未观察变为通过" in transitions["已知缺陷检出/正常版本误报"]["transition"]
    dims = {row["dimension"]: row for row in result["dimensions"]}
    assert dims["defect_detection"]["before"] is None and dims["defect_detection"]["delta"] is None
    assert dims["cleanup"]["delta"] == 0 and dims["cleanup"]["observed"]
    same = evaluation("c", "functional", "v1", "passed", {"计划执行范围完整": "passed"}, {"defect_detection": 4, "cleanup": 3}, source="run-2")
    assert compare(cand, same)["comparable"] is True
    other_target = evaluation("d", "business", "v1", "passed", {}, {})
    assert not compare(cand, other_target)["comparable"] and "评测对象不同" in compare(cand, other_target)["incompatible_reasons"]
    other_rubric = evaluation("e", "functional", "v2", "passed", {}, {}, source="run-2")
    assert any("评分口径版本不同" in reason for reason in compare(cand, other_rubric)["incompatible_reasons"])


def test_heldout_and_stability_endpoints_require_permissions(client, monkeypatch, tmp_path):
    headers, _ = operator(client, ["qa.view"])
    assert client.get("/api/v1/op/qa/agent-quality/heldout", headers=headers).status_code == 200
    assert client.post("/api/v1/op/qa/agent-quality/heldout/reveal", headers=headers,
                       json={"entry_id": "H-order-shortage", "reason": "复核需要"}).status_code == 403
    assert client.get("/api/v1/op/qa/agent-quality/stability?plan_id=missing", headers=headers).status_code == 404

    headers, _ = operator(client)
    view = client.get("/api/v1/op/qa/agent-quality/heldout", headers=headers).json()
    assert view["entries"] and all("expect" not in row for row in view["entries"])
    # 本机可能已由运营写入答案文件：两种状态都合法，但都不允许暴露期望值
    assert all(row["status"] in ("sealed", "expectation_unavailable") for row in view["entries"])
    if view["available"]:
        assert all(row["expect_hash"] for row in view["entries"])
    revealed = client.post("/api/v1/op/qa/agent-quality/heldout/reveal", headers=headers,
                           json={"entry_id": "H-order-shortage", "reason": "核对未公开期望"}).json()
    assert revealed["answer"]["status"] in ("revealed", "expectation_unavailable")
    audits = client.get("/api/v1/op/qa/agent-quality/heldout/reveals", headers=headers).json()
    assert audits and audits[0]["entry_id"] == "H-order-shortage" and audits[0]["reason"] == "核对未公开期望"