"""多场景已知缺陷基准：注入必须真的生效、必须被真实断言抓到、正常版不能误报。"""
import pytest

from app.quality import faults
from app.quality.agent_evaluation import calibrate_tester
from app.quality.catalog import FUNCTIONAL_TESTS, cases


def buyer(client):
    login = client.post("/api/v1/auth/login", json={"username": "alice", "password": "alice123"})
    login.raise_for_status()
    return {"Authorization": "Bearer " + login.json()["access_token"]}


def sku_id(client):
    return client.get("/api/v1/c/shops/nanzhi/products").json()[0]["skus"][0]["id"]


def test_scenario_table_is_registered_active_and_isolated_only():
    registered = {row["id"] for row in cases() if row["kind"] == "functional" and row["state"] == "active"}
    variants = [row["variant"] for row in faults.SCENARIOS]
    assert len(variants) == len(set(variants)) >= 4
    for row in faults.SCENARIOS:
        assert row["case_id"] in registered and row["case_id"] in FUNCTIONAL_TESTS, row
        assert row["defect"] and row["goal"] and row["marker"], row
    assert faults.scenario("wrong_freight")["case_id"] == "F13"
    assert faults.scenario("wrong_total")["case_id"] == "F19"
    assert faults.scenario("stock_over_add")["case_id"] == "F17"
    assert faults.scenario("buyer_merchant_access")["case_id"] == "F02"
    receipt = {}
    with pytest.raises(ValueError, match="仅限独立合成环境"):
        faults.apply("wrong_total", "real-nanzhi", receipt)
    assert faults.apply("not-a-variant", "isolated-local", receipt)() is None


def test_wrong_freight_and_wrong_total_really_change_money(client):
    headers = buyer(client)
    path = "/api/v1/c/shops/nanzhi/cart"
    receipt = {}
    restore = faults.apply("wrong_freight", "isolated-local", receipt)
    try:
        client.post(path, headers=headers, json={"sku_id": sku_id(client), "quantity": 1})
        cart = client.get(path, headers=headers).json()
        assert receipt["calls"] > 0 and cart["freight_yuan"] == receipt["injected"] == receipt["original"] + 1
    finally:
        restore()
    assert client.get(path, headers=headers).json()["freight_yuan"] == receipt["original"]

    total_receipt = {}
    restore = faults.apply("wrong_total", "isolated-local", total_receipt)
    try:
        order = client.post("/api/v1/c/shops/nanzhi/orders", headers=headers,
                            json={"sku_id": sku_id(client), "quantity": 1, "address": "缺陷基准合成地址"}).json()
        assert total_receipt["calls"] > 0 and order["total_yuan"] == total_receipt["injected"] == total_receipt["original"] + 100
    finally:
        restore()


def test_stock_over_add_and_buyer_merchant_access_really_break_the_rules(client):
    headers = buyer(client)
    products = client.get("/api/v1/c/shops/nanzhi/products").json()
    product = products[0]
    target, other = product["skus"][:2]
    shortage = {"sku_id": other["id"], "quantity": other["stock"] + 1, "address": "缺陷基准合成地址"}
    assert client.post("/api/v1/c/shops/nanzhi/orders", headers=headers, json=shortage).status_code == 400
    receipt = {}
    restore = faults.apply("stock_over_add", "isolated-local", receipt)
    try:
        accepted = client.post("/api/v1/c/shops/nanzhi/orders", headers=headers, json=shortage)
        assert accepted.status_code == 200, accepted.text
        assert receipt["calls"] > 0 and receipt["coerced"]["from"] == other["stock"] + 1 and receipt["coerced"]["to"] == 1
    finally:
        restore()
    assert client.post("/api/v1/c/shops/nanzhi/orders", headers=headers, json=shortage).status_code == 400
    assert target["stock"] > 1

    assert client.get("/api/v1/b/products", headers=headers).status_code == 403
    access = {}
    restore = faults.apply("buyer_merchant_access", "isolated-local", access)
    try:
        allowed = client.get("/api/v1/b/products", headers=headers)
        # 权限判定已被绕过：买家不再被 403 拒绝（该买家没有店铺，所以后续是 404）；F02 断言的正是 403，因此能抓到。
        assert allowed.status_code not in (401, 403), allowed.text
        assert access["calls"] > 0
    finally:
        restore()
    assert client.get("/api/v1/b/products", headers=headers).status_code == 403


class FakeExecutor:
    """按场景返回结果：注入版默认失败（模拟被测 Agent 检出），可用 undetected 指定漏检的场景。"""

    def __init__(self, undetected=(), silent=()):
        self.undetected = set(undetected)
        self.silent = set(silent)
        self.specs = []

    def __call__(self, spec, cancelled):
        self.specs.append(spec)
        variant = spec["calibration_variant"]
        injected = variant != "correct"
        receipt = {"variant": variant, "calls": 0 if variant in self.silent else 1}
        status = "passed" if (not injected or variant in self.undetected) else "failed"
        reports = [{"node": spec["case_id"], "stage": "call", "outcome": "failed" if status == "failed" else "passed"}]
        return {"status": status, "functional_agent": {"tools": ["read_bc_features", "execute_registered_case"]},
                "cleanup_ok": True, "calibration_receipt": receipt, "suite": {"reports": reports},
                "assertions": [{"name": "固定回归确实收集并执行且未跳过", "passed": status == "passed", "expected": "执行并通过", "actual": reports}]}


def test_calibration_covers_every_scenario_and_keeps_freight_semantics():
    executor = FakeExecutor()
    result = calibrate_tester(executor)
    assert [row["variant"] for row in result["scenarios"]] == [row["variant"] for row in faults.SCENARIOS]
    assert result["scenarios_detected"] and not result["scenarios_false_positive"] and result["scenarios_valid"]
    assert result["detected"] and not result["false_positive"] and result["valid"]      # 运费口径保持不变
    assert len(result["runs"]) == 2 and result["runs"][0]["variant"] == "correct"
    assert all(row["mutation_exercised"] for row in result["scenarios"])
    assert "不代表全站缺陷检出率" in result["scope"] and "库存" in result["scope"]
    # 每个场景都跑正常版+注入版，且用例是该场景登记的用例
    assert len(executor.specs) == 2 * len(faults.SCENARIOS)
    assert {spec["case_id"] for spec in executor.specs} == {row["case_id"] for row in faults.SCENARIOS}


def test_calibration_reports_missed_detection_and_unexercised_injection():
    missed = calibrate_tester(FakeExecutor(undetected={"stock_over_add"}))
    assert missed["scenarios_detected"] is False
    assert next(row for row in missed["scenarios"] if row["variant"] == "stock_over_add")["detected"] is False
    silent = calibrate_tester(FakeExecutor(silent={"buyer_merchant_access"}))
    row = next(item for item in silent["scenarios"] if item["variant"] == "buyer_merchant_access")
    assert silent["scenarios_detected"] is False and row["mutation_exercised"] is False
    # 正常版失败必须记为误报，不能算检出
    class FalsePositive(FakeExecutor):
        def __call__(self, spec, cancelled):
            output = super().__call__(spec, cancelled)
            if spec["calibration_variant"] == "correct":
                output["status"] = "failed"
            return output
    noisy = calibrate_tester(FalsePositive())
    assert noisy["scenarios_false_positive"] and noisy["scenarios_valid"]
    assert all(row["false_positive"] for row in noisy["scenarios"])