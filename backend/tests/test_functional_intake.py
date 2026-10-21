from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.quality import QualityPlan, QualityRun
from app.quality import intake_driver
from app.quality.worker import child_module
from test_quality import operator


def verdict(**over):
    body = {"feasible": True, "reason": "目录中购物车域有已登记的复合工具", "feature_ids": ["cart"],
            "case_ids": ["F11"], "missing": []}
    body.update(over)
    return body


def stub(monkeypatch, payload):
    from app.core.config import settings
    monkeypatch.setattr(settings, "qa_chat_model", "test-model")
    monkeypatch.setattr(settings, "qa_chat_api_key_file", "external-test-key.txt")
    seen = {}

    def execute(spec, cancelled):
        seen.update(spec)
        return {"status": "completed", "tools": [{"tool": "read_bc_features"}], "budget": {"calls": 2, "tokens": 1100}, **payload}

    monkeypatch.setattr("app.quality.worker.subprocess_job", execute)
    return seen


def post(client, headers, **over):
    body = {"requirement": "验证 C 端购物车修改数量超过库存会被拒绝，且金额与库存不变", "environment_id": "isolated-local"}
    body.update(over)
    return client.post("/api/v1/op/qa/functional-intake", headers=headers, json=body)


def test_intake_requires_functional_permission(client, monkeypatch):
    headers, _ = operator(client, ["qa.view"])
    assert post(client, headers).status_code == 403
    headers, _ = operator(client)
    assert post(client, headers, environment_id="real-nanzhi-typo").status_code == 422


def test_intake_returns_approvable_plan_only_for_registered_cases(client, monkeypatch):
    headers, _ = operator(client)
    seen = stub(monkeypatch, {"verdict": verdict()})
    response = post(client, headers)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["status"] == "completed" and record["verdict"]["feasible"] is True
    assert seen["intake_job"] is True and seen["case_id"] == "__functional_intake__"
    assert seen["feature_catalog"]["version"] and seen["environment_id"] == "isolated-local"
    plan = record["plan"]
    assert plan["kind"] == "functional" and plan["planner"] == "model" and plan["diagnostic"] is False
    assert plan["functional_driver"] is True and plan["case_ids"] == ["F11"] and plan["mode"] == "rules"
    assert "购物车" in plan["goal"]
    # 受理依据全量目录判断，计划绑定的是所选用例子集版本；两个版本都必须写清楚。
    assert record["catalog_version"] == seen["feature_catalog"]["version"]
    assert record["plan_catalog_version"] and record["plan_catalog_version"] != record["catalog_version"]
    assert record["plan_catalog_version"][:12] in plan["goal"] and record["catalog_version"][:12] in plan["goal"]
    # 受理产出的计划必须能通过既有审批链，并绑定同一版本的功能目录。
    created = client.post("/api/v1/op/qa/plans", headers=headers, json=plan)
    assert created.status_code == 201, created.text
    payload = created.json()["payload"]
    assert payload["feature_catalog"]["version"] == record["plan_catalog_version"]
    assert payload["functional_driver"] is True and payload["case_ids"] == ["F11"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(QualityRun)) == 0
        assert db.scalar(select(func.count()).select_from(QualityPlan)) == 1
    assert client.get("/api/v1/op/qa/functional-intake", headers=headers).json()[0]["id"] == record["id"]


def test_intake_reports_uncovered_and_rejects_non_testable_cases(client, monkeypatch):
    headers, _ = operator(client)
    uncovered = verdict(feasible=False, reason="目录里没有秒杀促销功能", feature_ids=[], case_ids=[], missing=["缺少秒杀促销功能与对应执行工具"])
    stub(monkeypatch, {"verdict": uncovered})
    record = post(client, headers, requirement="验证秒杀促销活动的限购规则").json()
    assert record["status"] == "completed" and record["plan"] is None
    assert record["verdict"]["missing"] and "秒杀" in record["verdict"]["missing"][0]
    # 模型给出的非功能用例或未登记用例不能变成计划；只记录为阻塞。
    stub(monkeypatch, {"verdict": verdict(case_ids=["A01"])})
    blocked = post(client, headers).json()
    assert blocked["status"] == "blocked" and blocked["plan"] is None and "没有可提交" in blocked["error"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(QualityPlan)) == 0


class Response:
    def __init__(self, calls):
        self.content = ""
        self.tool_calls = calls


class Model:
    def __init__(self, script):
        self.script = list(script)

    def bind_tools(self, tools):
        self.tools = {tool.name: tool for tool in tools}
        return self

    def invoke(self, messages):
        return self.script.pop(0) if self.script else Response([])


def snapshot():
    return {"version": "a" * 64, "endpoint_count": 3, "frontend": [{"side": "C", "route_literals": ["#/cart"]}],
            "features": [{"id": "cart", "name": "购物车与结算", "sides": ["C"], "rule": "数量合法、运费优惠一致",
                          "coverage": "partial_registered",
                          "tools": [{"case_id": "F11", "title": "购物车数量校验", "environments": ["isolated-local"]}]},
                         {"id": "chat", "name": "业务助手", "sides": ["B", "C"], "rule": "角色边界", "coverage": "uncovered", "tools": []}]}


def spec(**over):
    body = {"environment_id": "isolated-local", "requirement": "验证购物车数量上限", "max_calls": 3, "max_tokens": 500}
    body.update(over)
    return body


def test_intake_driver_requires_catalog_read_and_registered_tools():
    read = Response([{"name": "read_bc_features", "args": {}, "id": "1"}])
    submit = Response([{"name": "submit_feasibility", "id": "2", "args": {"feasible": True, "reason": "有工具", "feature_ids": ["cart"], "case_ids": ["F11"]}}])
    model = Model([read, submit])
    result = intake_driver.judge(spec(), model, snapshot())
    assert result["status"] == "completed" and result["verdict"]["case_ids"] == ["F11"]
    # 受限工具必须真正绑定给模型，否则模型只会文字作答，受理永远拿不到判断。
    assert set(model.tools) == {"read_bc_features", "submit_feasibility"}
    assert [row["tool"] for row in result["tools"]] == ["read_bc_features", "submit_feasibility"]
    assert result["conversation"][0]["content"] == "验证购物车数量上限"
    # 未读目录、未登记用例、以及判为不可测却不说缺什么，都必须被拒绝。
    with pytest.raises(ValueError, match="必须先读取功能目录"):
        intake_driver.judge(spec(), Model([submit]), snapshot())
    with pytest.raises(ValueError, match="已登记"):
        intake_driver.judge(spec(), Model([read, Response([{"name": "submit_feasibility", "id": "2", "args": {"feasible": True, "reason": "猜测", "feature_ids": ["cart"], "case_ids": ["F99"]}}])]), snapshot())
    with pytest.raises(ValueError, match="缺少什么"):
        intake_driver.judge(spec(), Model([read, Response([{"name": "submit_feasibility", "id": "2", "args": {"feasible": False, "reason": "未实现"}}])]), snapshot())
    assert intake_driver.judge(spec(), Model([Response([])]), snapshot())["status"] == "blocked"


def test_intake_child_process_is_its_own_module():
    assert child_module({"intake_job": True}, False, False) == "app.quality.intake_driver"
    assert child_module({"evaluation_job": True}, False, False) == "app.quality.evaluation_driver"
    assert child_module({}, True, False) == "app.quality.planner"
    assert child_module({"functional_driver": True}, False, True) == "app.quality.functional_driver"
    assert child_module({"environment_id": "real-nanzhi"}, False, False) == "app.quality.real_runner"
    assert child_module({"environment_id": "isolated-local"}, False, False) == "app.quality.case_runner"