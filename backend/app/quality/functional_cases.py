import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResponseCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(default="", max_length=100, pattern=r"^(?:[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+){0,7})?$")
    operator: Literal["equals", "contains", "length"] = "equals"
    value: str | int | float | bool | None = Field(default=None)

    @model_validator(mode="after")
    def bounded_value(self):
        if isinstance(self.value, str) and len(self.value) > 200:
            raise ValueError("断言文字最多200字")
        if self.operator == "length" and (type(self.value) is not int or not 0 <= self.value <= 1000):
            raise ValueError("长度断言需为0至1000整数")
        return self


class FunctionalStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["catalog", "product", "cart", "add_cart", "orders"]
    role: Literal["customer", "merchant", "anonymous"] = "customer"
    product_id: int | None = Field(default=None, ge=1)
    sku_id: int | None = Field(default=None, ge=1)
    quantity: int = Field(default=1, ge=-1, le=100)
    expected_status: Literal[200, 201, 400, 401, 403, 404, 409, 422] = 200
    checks: list[ResponseCheck] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def required_parameters(self):
        if self.action == "product" and self.product_id is None:
            raise ValueError("商品详情需要商品ID")
        if self.action == "add_cart" and self.sku_id is None:
            raise ValueError("加购需要SKU ID")
        return self


class FunctionalCaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["functional"]
    title: str = Field(min_length=2, max_length=80)
    steps: list[FunctionalStep] = Field(min_length=1, max_length=12)


def read_path(value, path):
    for key in path.split(".") if path else []:
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and re.fullmatch(r"\d+", key) and int(key) < len(value):
            value = value[int(key)]
        else:
            raise AssertionError("响应字段不存在：" + path)
    return value


def execute_functional(definition, evidence):
    from fastapi.testclient import TestClient
    from app.main import app

    body = FunctionalCaseIn.model_validate(definition)
    reports = []
    with TestClient(app) as client:
        headers = {"anonymous": {}}
        for role, username in (("customer", "alice"), ("merchant", "merchant")):
            response = client.post("/api/v1/auth/login", json={"username": username, "password": username + "123"})
            evidence.check("合成身份登录：" + role, response.status_code == 200)
            headers[role] = {"Authorization": "Bearer " + response.json()["access_token"]}
        for index, step in enumerate(body.steps, 1):
            prefix = "/api/v1/c/shops/nanzhi"
            method = "POST" if step.action == "add_cart" else "GET"
            path = {"catalog": prefix + "/products", "product": prefix + f"/products/{step.product_id}",
                    "cart": prefix + "/cart", "add_cart": prefix + "/cart", "orders": "/api/v1/c/orders"}[step.action]
            kwargs = {"json": {"sku_id": step.sku_id, "quantity": step.quantity}} if step.action == "add_cart" else {}
            response = client.request(method, path, headers=headers[step.role], **kwargs)
            evidence.check(f"步骤{index} {step.action} HTTP状态", response.status_code == step.expected_status,
                           step.expected_status, response.status_code)
            data = response.json()
            for check in step.checks:
                actual = read_path(data, check.path)
                passed = (type(actual) is type(check.value) and actual == check.value) if check.operator == "equals" else (
                    isinstance(actual, str) and isinstance(check.value, str) and check.value in actual
                    or isinstance(actual, (list, dict)) and check.value in actual) if check.operator == "contains" else (
                    isinstance(actual, (str, list, dict)) and len(actual) == check.value)
                evidence.check(f"步骤{index} 字段{check.path or '根响应'} {check.operator}", passed, check.value, actual)
            reports.append({"node": f"declarative_functional::step_{index}_{step.action}", "stage": "call", "outcome": "passed"})
    return {"suite": {"adapter": "declarative_functional", "reports": reports},
            "facts": {"scope": "白名单业务动作，独立合成店铺", "steps": len(body.steps)}}
