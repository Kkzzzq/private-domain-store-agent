import re
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.models.quality import QualityCaseVersion
from app.quality.catalog import content_digest, case_by_id, cases
from app.quality.functional_cases import FunctionalCaseIn


class TurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=2, max_length=1000)
    required_tools: list[str] = Field(default_factory=list, max_length=5)
    expected_contains: list[str] = Field(default_factory=list, max_length=8)
    forbidden_contains: list[str] = Field(default_factory=list, max_length=8)
    max_product_price: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounded_assertions(self):
        from app.agent.tools import SPECS
        if not set(self.required_tools).issubset(SPECS):
            raise ValueError("只允许已登记的业务工具断言")
        if any(not word.strip() or len(word) > 100 for word in self.expected_contains + self.forbidden_contains):
            raise ValueError("断言文字需为1到100字")
        if not self.required_tools and not self.expected_contains and not self.forbidden_contains and self.max_product_price is None:
            raise ValueError("每轮必须配置至少一个硬断言")
        return self


class CaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=80)
    role: str = Field(default="customer", pattern="^(customer|merchant)$")
    turns: list[TurnIn] = Field(min_length=1, max_length=5)


def custom_id(case_id):
    return bool(re.fullmatch(r"C[a-f0-9]{11}", case_id))


def snapshot(row):
    kind = row.specification.get("kind", "assistant")
    return {"id": row.id, "family_id": row.family_id, "title": row.specification["title"], "kind": kind, "version": row.version,
            "state": row.state, "modes": ["rules"] if kind == "functional" else ["live"], "adapter": "declarative_" + kind, "critical": True,
            "definition": row.specification, "revision_digest": content_digest(row.specification)}


def all_cases(db):
    return cases() + [snapshot(row) for row in db.scalars(select(QualityCaseVersion).order_by(QualityCaseVersion.created_at))]


def resolve(db, case_id):
    if not custom_id(case_id):
        return case_by_id(case_id)
    row = db.get(QualityCaseVersion, case_id, populate_existing=True)
    return snapshot(row) if row else None


def create(db, user_id, body, previous=None):
    specification = body.model_dump()
    if previous and previous.specification.get("kind", "assistant") != specification.get("kind", "assistant"):
        raise HTTPException(409, "用例版本不能跨类型修改")
    case_id = "C" + uuid4().hex[:11]
    family = previous.family_id if previous else case_id
    version = (db.scalar(select(func.max(QualityCaseVersion.version)).where(QualityCaseVersion.family_id == family)) or 0) + 1
    row = QualityCaseVersion(id=case_id, family_id=family, version=version, created_by=user_id, state="candidate", specification=specification)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "用例版本发生并发冲突，请重试") from None
    return snapshot(row)


def validate_snapshots(db, snapshots):
    for expected in snapshots:
        if expected.get("adapter") not in ("declarative_assistant", "declarative_functional"):
            continue
        actual = resolve(db, expected["id"])
        if not actual or actual["state"] != "active" or actual["revision_digest"] != expected["revision_digest"]:
            raise HTTPException(409, "自定义用例已撤销或版本不一致")


def execute_definition(definition, evidence):
    from fastapi.testclient import TestClient
    from app.core.config import settings
    from app.main import app
    from app.db.session import SessionLocal
    from app.models.tables import AgentToolLog, User
    settings.agent_mode = "auto"
    settings.agent_require_llm = True
    specification = CaseIn.model_validate(definition)
    transcript = []
    with TestClient(app) as client:
        username = "merchant" if specification.role == "merchant" else "alice"
        response = client.post("/api/v1/auth/login", json={"username": username, "password": username + "123"})
        evidence.check("自定义场景合成身份登录", response.status_code == 200)
        headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        with SessionLocal() as db:
            user_id = db.scalar(select(User.id).where(User.username == username))
        session = None
        for turn in specification.turns:
            with SessionLocal() as db:
                audit_start = db.scalar(select(func.max(AgentToolLog.id))) or 0
            path = "/api/v1/b/chat" if specification.role == "merchant" else "/api/v1/c/shops/nanzhi/chat"
            response = client.post(path, headers=headers, json={"message": turn.message, "session_id": session})
            if response.status_code == 503:
                raise RuntimeError("自定义真实模型场景未完成，不能降级通过")
            evidence.check("自定义业务助手请求成功", response.status_code == 200)
            output = response.json();session = output["session_id"]
            transcript.append({"input": turn.message, "output": output})
            evidence.check("真实模型而非规则回退", output["mode"] == "llm")
            with SessionLocal() as db:
                audit = [{"id": row.id, "tool": row.tool, "ok": row.ok, "flag": row.flag}
                         for row in db.scalars(select(AgentToolLog).where(
                             AgentToolLog.id > audit_start, AgentToolLog.user_id == user_id,
                             AgentToolLog.session_id == session).order_by(AgentToolLog.id))]
            transcript[-1]["tool_audit"] = audit
            for tool in turn.required_tools:
                evidence.check("必需工具：" + tool,
                               any(row["tool"] == tool for row in output["tools"])
                               and any(row["tool"] == tool and row["ok"] for row in audit),
                               "本轮真实工具审计成功", audit)
            for word in turn.expected_contains:
                evidence.check("回答应包含：" + word, word in output["answer"])
            for word in turn.forbidden_contains:
                evidence.check("回答不得包含：" + word, word not in output["answer"])
            if turn.max_product_price is not None:
                evidence.check("商品卡符合价格上限", bool(output["products"]) and all(row["price_from"] <= turn.max_product_price for row in output["products"]))
    return {"transcript": transcript, "facts": {"assertion_source": "OP批准的声明式用例版本，不执行自定义代码/SQL/URL"}}
