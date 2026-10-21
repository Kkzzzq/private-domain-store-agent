"""功能测试 Agent 组合点击工具的真实证据（默认跳过，需要模型额度与浏览器）。

运行：QA_LIVE_UI_AGENT=1 pytest tests/test_ui_action_agent_live.py -q -s
证明链路：读功能目录 → 调用登记的点击工具用例 → 真实页面点击 + 接口交叉核验 → 硬断言与清理。
"""
import json
import os
from pathlib import Path

import pytest

from app.core.config import settings
from app.quality.catalog import case_by_id
from app.quality.feature_catalog import catalog
from app.quality.ui_actions import catalog_rows


pytestmark = pytest.mark.skipif(os.environ.get("QA_LIVE_UI_AGENT") != "1",
                                reason="点击工具 Agent 实跑需要 QA_LIVE_UI_AGENT=1（会消耗模型额度并启动浏览器）")


def load_qa_profile():
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("QA_CHAT_") and "=" in line:
            key, value = line.split("=", 1)
            setattr(settings, key.strip().lower(), value.strip())
    return bool(settings.qa_chat_model and settings.qa_chat_api_key_file)


def run_registered(case_id, goal, tmp_path):
    from app.quality.worker import subprocess_job
    snapshot = case_by_id(case_id)
    spec = {"goal": goal, "kind": "functional", "case_id": case_id, "case_ids": [case_id],
            "case_snapshots": [snapshot], "feature_catalog": catalog([snapshot]), "functional_driver": True,
            "environment_id": "isolated-local", "mode": "rules", "max_calls": 4, "max_tokens": 60000,
            "timeout_seconds": 300}
    output = subprocess_job(spec, lambda: False)
    (tmp_path / f"{case_id}.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def test_agent_runs_a_single_click_tool(tmp_path):
    if not load_qa_profile():
        pytest.skip("本机 .env 未配置 QA_CHAT_MODEL / QA_CHAT_API_KEY_FILE")
    case = next(row for row in catalog_rows() if row.get("ui_action") == "c_open_shop_home")
    output = run_registered(case["id"], "用登记的点击工具打开买家店铺首页：先读功能目录，再执行该用例并如实报告。", tmp_path)
    agent = output.get("functional_agent") or {}
    calls = [row.get("tool") for row in agent.get("tools", [])]
    assertions = {row["name"]: row["passed"] for row in output.get("assertions", [])}
    print("单动作用例轨迹：", calls, "断言：", json.dumps(assertions, ensure_ascii=False))
    assert output["status"] == "passed", output.get("error")
    assert calls[0] == "read_bc_features" and calls.count("execute_registered_case") >= 1
    assert assertions.get("点击工具·打开买家首页：搜索框可见") is True, assertions
    assert (output.get("suite") or {}).get("adapter") == "ui_action_script", output.get("suite")
    assert output.get("cleanup_ok") is True


def test_agent_runs_the_composite_buyer_click_flow(tmp_path):
    if not load_qa_profile():
        pytest.skip("本机 .env 未配置 QA_CHAT_MODEL / QA_CHAT_API_KEY_FILE")
    case = next(row for row in catalog_rows() if row.get("ui_flow") == "flow_c_buy")
    output = run_registered(case["id"], "组合点击完成一次买家下单链（选规格、加购、结算、提交订单）：先读功能目录，再执行该用例并如实报告。", tmp_path)
    artifacts = Path(__file__).resolve().parents[1] / "data" / "acceptance"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "ui-action-agent-live.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    agent = output.get("functional_agent") or {}
    calls = [row.get("tool") for row in agent.get("tools", [])]
    assertions = {row["name"]: row["passed"] for row in output.get("assertions", [])}
    print("复合动作流轨迹：", calls)
    print("断言：", json.dumps(assertions, ensure_ascii=False))
    assert output["status"] == "passed", output.get("error")
    assert calls[0] == "read_bc_features" and calls.count("execute_registered_case") >= 1
    # 页面点击与接口事实都要在断言里体现，不能只看页面提示
    assert assertions.get("点击工具·点击商品卡片进入详情") is True, assertions
    assert assertions.get("点击工具·加入购物车：购物车接口确有该商品且数量一致") is True, assertions
    assert assertions.get("点击工具·提交订单：订单接口新增一笔") is True, assertions
    assert (output.get("suite") or {}).get("adapter") == "ui_action_script"
    assert output.get("cleanup_ok") is True and (output.get("budget") or {}).get("calls", 0) > 0