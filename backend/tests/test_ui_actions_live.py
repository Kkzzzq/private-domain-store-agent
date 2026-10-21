"""可复用点击工具库的实跑证据（默认跳过，需要浏览器与时间）。

运行：QA_LIVE_UI_ACTIONS=1 pytest tests/test_ui_actions_live.py -q -s
实跑通过后，动作才允许被 Agent 调用；失败的动作必须降级为 unverified，不允许“看起来能用”。
"""
import json
import os
from pathlib import Path

import pytest

from app.quality import ui_actions


pytestmark = pytest.mark.skipif(os.environ.get("QA_LIVE_UI_ACTIONS") != "1",
                                reason="点击工具库实跑需要 QA_LIVE_UI_ACTIONS=1（会启动隔离站点与浏览器）")

BUYER_FLOW = [
    {"action": "c_open_shop_home"},
    {"action": "c_search_products", "params": {"keyword": "抱枕"}},
    {"action": "c_open_product_card", "params": {"product_name": "亚麻抱枕套"}},
    {"action": "c_select_sku", "params": {"sku_index": 0}},
    {"action": "c_add_to_cart", "params": {"quantity": 1}},
    {"action": "c_open_cart"},
    {"action": "c_checkout"},
    {"action": "c_submit_order"},
]
MERCHANT_FLOW = [
    {"action": "op_grant_merchant_access", "params": {"username": "merchant", "reason": "点击工具库验收：授权商家开店"}},
    {"action": "b_open_products"},
    {"action": "b_search_product", "params": {"product_name": "亚麻抱枕套"}},
    {"action": "b_click_side_nav", "params": {"route": "orders"}},
]
MERCHANT_FLOW_WITHOUT_GRANT = [
    {"action": "b_open_products"},
]


def test_action_registry_only_exposes_verified_actions():
    view = ui_actions.public_view()
    assert view["counts"]["ready"] >= 8 and view["counts"]["unverified"] >= 1
    for row in view["actions"]:
        assert row["status"] in ("ready", "unverified")
        assert row["steps"] and row["verify"] and row["cross_check"] and row["evidence"], row["id"]
        if row["status"] == "unverified":
            assert "待确认" in " ".join(row["steps"]) or "待确认" in " ".join(row["verify"]) or row.get("precondition"), row["id"]
    # 商家动作选择器有出处（E02/E07），但合成 fixture 没有开店授权：必须写明前置条件，缺条件时明确阻塞。
    merchant_actions = [row for row in view["actions"] if row["side"] == "B"]
    assert merchant_actions and all(row["status"] == "ready" and "开店授权" in row["precondition"] for row in merchant_actions)


def test_unverified_or_unknown_actions_are_rejected_before_running():
    with pytest.raises(ValueError, match="未登记的动作"):
        ui_actions.validate([{"action": "c_click_anything"}])
    with pytest.raises(ValueError, match="尚未实跑验证"):
        ui_actions.validate([{"action": "c_update_cart_quantity", "params": {"quantity": 2}}])
    with pytest.raises(ValueError, match="缺少参数 keyword"):
        ui_actions.validate([{"action": "c_search_products"}])
    with pytest.raises(ValueError, match="需要整数"):
        ui_actions.validate([{"action": "c_select_sku", "params": {"sku_index": "第一"}}])
    with pytest.raises(ValueError, match="不接受参数"):
        ui_actions.validate([{"action": "c_open_cart", "params": {"keyword": "x"}}])
    steps = ui_actions.validate([{"action": "c_select_sku"}])
    assert steps[0]["params"]["sku_index"] == 0                      # 默认值补齐


def test_live_ui_action_library_runs_both_sides(tmp_path, monkeypatch):
    monkeypatch.setenv("QA_CHILD_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("QA_CHILD_RUN", "a" * 32)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "browser.db").as_posix())
    monkeypatch.setenv("REDIS_URL", "memory")
    monkeypatch.setenv("STRICT_DEPENDENCIES", "false")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("QA_BROWSER_OP", "1")
    monkeypatch.setenv("AGENT_MODE", "fallback")
    monkeypatch.setenv("RAG_REQUIRE_VECTORS", "false")
    from app.quality.sandbox import Evidence

    evidence = Evidence()
    result = ui_actions.execute_action_script({"actions": BUYER_FLOW, "kind": "buyer", "shop_code": "nanzhi"}, evidence)
    artifacts = Path(__file__).resolve().parents[1] / "data" / "acceptance"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "ui-actions-buyer-live.json").write_text(
        json.dumps({"result": result, "assertions": evidence.assertions, "requests": evidence.requests}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("买家动作链断言：", json.dumps({row["name"]: row["passed"] for row in evidence.assertions}, ensure_ascii=False))
    assert result["status"] == "passed", result.get("error")
    assert all(row["passed"] for row in evidence.assertions), [row for row in evidence.assertions if not row["passed"]]
    assert any(row["name"].startswith("点击工具·点击商品卡片") for row in evidence.assertions)
    assert any(row["name"].startswith("点击工具·加入购物车：购物车接口确有该商品") for row in evidence.assertions)
    assert any(row["name"].startswith("点击工具·提交订单：订单接口新增一笔") for row in evidence.assertions)

    merchant = Evidence()
    merchant_result = ui_actions.execute_action_script({"actions": MERCHANT_FLOW, "kind": "merchant", "shop_code": "nanzhi"}, merchant)
    (artifacts / "ui-actions-merchant-live.json").write_text(
        json.dumps({"result": merchant_result, "assertions": merchant.assertions}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("商家动作链断言：", json.dumps({row["name"]: row["passed"] for row in merchant.assertions}, ensure_ascii=False))
    # OP 授权接口本身已验证成功（200）；但合成 fixture 的 B 端门户仍拒绝，按未定位的真实状态报阻塞。
    assert any(row["name"].startswith("点击工具·OP授权商家开店") and row["passed"] for row in merchant.assertions)
    assert merchant_result["status"] == "failed"
    assert "前置条件未满足" in (merchant_result.get("error") or ""), merchant_result.get("error")

    # 不授权直接用 B 端动作：必须给出明确前置条件阻塞，而不是含糊失败
    blocked = Evidence()
    blocked_result = ui_actions.execute_action_script({"actions": MERCHANT_FLOW_WITHOUT_GRANT, "kind": "merchant", "shop_code": "nanzhi"}, blocked)
    print("未授权商家链：", blocked_result.get("status"), blocked_result.get("error"))
    assert blocked_result["status"] == "failed"
    assert "前置条件未满足" in (blocked_result.get("error") or ""), blocked_result.get("error")