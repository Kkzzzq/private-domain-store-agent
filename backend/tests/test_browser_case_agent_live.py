"""浏览器用例经功能测试 Agent 自主执行的实时证据（默认跳过，避免 CI 消耗额度与浏览器时间）。

运行：QA_LIVE_BROWSER=1 pytest tests/test_browser_case_agent_live.py -q -s
要求同时满足：Agent 先读功能目录再调用执行工具、用例走浏览器适配器、请求里带真实浏览器标记、
页面操作后由接口独立核验业务状态（不能只看页面出现“成功”）。
"""
import json
import os
from pathlib import Path

import pytest

from app.core.config import settings
from app.quality.feature_catalog import catalog


pytestmark = pytest.mark.skipif(os.environ.get("QA_LIVE_BROWSER") != "1",
                                reason="浏览器用例 Agent 实跑需要 QA_LIVE_BROWSER=1（会消耗模型额度并启动浏览器）")

CASE = {"id": "E01", "kind": "functional", "state": "active", "title": "买家规格加购用券结算",
        "adapter": "registered_browser", "modes": ["rules"], "environments": ["isolated-local", "native-local"]}


def load_qa_profile():
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("QA_CHAT_") and "=" in line:
            key, value = line.split("=", 1)
            setattr(settings, key.strip().lower(), value.strip())
    return bool(settings.qa_chat_model and settings.qa_chat_api_key_file)


def test_live_browser_case_runs_through_the_agent(tmp_path):
    if not load_qa_profile():
        pytest.skip("本机 .env 未配置 QA_CHAT_MODEL / QA_CHAT_API_KEY_FILE")
    from app.quality.worker import subprocess_job

    snapshot = catalog([CASE])
    cart = next(row for row in snapshot["features"] if row["id"] == "cart")
    assert cart["coverage_split"]["page"]["case_ids"] == ["E01"], cart["coverage_split"]   # 页面通道
    assert next(row for row in cart["tools"] if row["case_id"] == "E01")["channel"] == "page"

    spec = {"goal": "检查 C 端买家从商品详情选规格、加入购物车、用券结算到提交订单的页面链路：先读功能目录，再执行批准的 E01 并如实报告。",
            "kind": "functional", "case_id": "E01", "case_ids": ["E01"], "case_snapshots": [CASE],
            "feature_catalog": snapshot, "functional_driver": True, "environment_id": "isolated-local",
            "mode": "rules", "max_calls": 4, "max_tokens": 60000, "timeout_seconds": 120}
    output = subprocess_job(spec, lambda: False)
    (tmp_path / "browser-case-agent-live.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    artifacts = Path(__file__).resolve().parents[1] / "data" / "acceptance"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "browser-case-agent-live.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    agent = output.get("functional_agent") or {}
    tools = agent.get("tools", [])
    calls = [row.get("tool") for row in tools]
    executions = [row for row in tools if row.get("tool") == "execute_registered_case"]
    browser_requests = [row for row in output.get("requests", []) if row.get("via") == "real_browser"]
    assertions = {row["name"]: row["passed"] for row in output.get("assertions", [])}
    print("浏览器用例 Agent 轨迹：", calls)
    print("真实浏览器请求数：", len(browser_requests), "断言：", json.dumps(assertions, ensure_ascii=False))
    print("suite：", json.dumps(output.get("suite"), ensure_ascii=False)[:400])

    assert output["status"] == "passed", output.get("error")
    # 必须先读目录再执行；模型可能重复请求执行，重复只能返回既有结果、不能重放写入。
    assert calls[0] == "read_bc_features", calls
    assert executions and calls.index("execute_registered_case") > calls.index("read_bc_features"), calls
    assert executions[0]["args"]["case_id"] == "E01" and executions[0]["args"]["feature_id"] == "cart", executions[0]["args"]
    assert executions[0]["result"]["status"] == "passed", executions[0]["result"]
    assert all(row["result"].get("replayed") is False for row in executions[1:]), executions[1:]
    assert (output.get("suite") or {}).get("adapter") == "registered_browser", output.get("suite")
    # 页面确实被操作：请求来自真实浏览器，而不是只调接口
    assert browser_requests, output.get("requests")
    # 页面操作后再用接口独立核验业务状态，而不是以页面出现“成功”作为通过依据
    assert assertions.get("真实浏览器提交订单且优惠抵扣") is True, assertions
    assert assertions.get("浏览器提交订单接口真实成功") is True, assertions
    assert output.get("cleanup_ok") is True
    assert (output.get("budget") or {}).get("calls", 0) > 0