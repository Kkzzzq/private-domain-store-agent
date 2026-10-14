import json
import time

from pydantic import ValidationError

from app.agent.tools import IMPL, SPECS, allowed_tools
from app.agent.context import current
from app.agent.audit import record


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
    started = time.monotonic()
    args = _normalize_args(raw_args)
    def finish(result, ok=True, flag=""):
        record(name, args, ok, int((time.monotonic() - started) * 1000), flag)
        return result

    if name not in allowed_tools(current()[1].role):
        return finish("不支持的工具或无权调用。", False, "forbidden_tool")
    if set(args) & {"user_id", "shop_id", "role", "username"}:
        return finish("参数无效：不允许指定其他身份或店铺。", False, "identity_override")
    spec = SPECS.get(name)
    func = IMPL.get(name)
    if spec is None or func is None:
        return finish("不支持的工具。", False, "unknown_tool")
    try:
        parsed = spec.model_validate(_normalize_args(raw_args))
    except ValidationError as exc:
        loc = ".".join(str(part) for part in exc.errors()[0]["loc"])
        return finish(f"参数缺失或无效：{loc}", False, "invalid_args")

    for _ in range(2):
        try:
            result = str(func(**parsed.model_dump()))
            denied = result.startswith("没有找到这个订单")
            return finish(result, not denied, "order_not_found_or_denied" if denied else "")
        except Exception:
            pass
    return finish("工具执行失败，请稍后重试。", False, "execution_error")
