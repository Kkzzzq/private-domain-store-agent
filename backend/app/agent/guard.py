import json

from pydantic import ValidationError

from app.agent.tools import IMPL, SPECS


def _normalize_args(raw) -> dict:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(raw, dict):
        return raw
    return {}


def execute_tool(name: str, raw_args) -> str:
    spec = SPECS.get(name)
    func = IMPL.get(name)
    if spec is None or func is None:
        return "不支持的工具。"
    try:
        parsed = spec.model_validate(_normalize_args(raw_args))
    except ValidationError as exc:
        loc = ".".join(str(part) for part in exc.errors()[0]["loc"])
        return f"参数缺失或无效：{loc}"

    last_error: Exception | None = None
    for _ in range(2):
        try:
            return str(func(**parsed.model_dump()))
        except Exception as exc:
            last_error = exc
    return f"工具执行失败，请稍后重试。{last_error}"
