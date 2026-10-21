from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DebugIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["customer", "merchant"] = "customer"
    messages: list[str] = Field(min_length=1, max_length=5)
    confirmed: Literal[True]

    @field_validator("messages")
    @classmethod
    def clean_messages(cls, values):
        if any(not 2 <= len(value.strip()) <= 1000 for value in values):
            raise ValueError("每轮问题需为2到1000字")
        return [value.strip() for value in values]


def execute_dialogue(spec, evidence):
    from fastapi.testclient import TestClient
    from app.core.config import settings
    from app.main import app

    body = DebugIn.model_validate(spec["dialogue"])
    settings.agent_mode = "auto"
    settings.agent_require_llm = True
    transcript = []
    session = None
    with TestClient(app) as client:
        username = "merchant" if body.role == "merchant" else "alice"
        login = client.post("/api/v1/auth/login", json={"username": username, "password": username + "123"})
        evidence.check("合成身份可访问", login.status_code == 200)
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        for message in body.messages:
            response = client.post("/api/v1/b/chat" if body.role == "merchant" else "/api/v1/c/shops/nanzhi/chat",
                                   headers=headers, json={"message": message, "session_id": session})
            if response.status_code != 200:
                raise RuntimeError("真实业务助手请求未完成，未使用规则答案补齐")
            output = response.json()
            if output.get("mode") != "llm":
                raise RuntimeError("调试没有真实模型回答，不能标记完成")
            session = output["session_id"]
            transcript.append({"input": message, "output": output})
    return {"transcript": transcript, "facts": {"scope": "独立合成身份与数据，不评价答案正确性"}}
