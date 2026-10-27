import json
import time

from pydantic import ValidationError
from fastapi import HTTPException

from app.agent.tools import IMPL, SPECS, allowed_tools
from app.agent.context import current
from app.agent.audit import record


def _normalize_args(raw) -> dict:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("工具参数不是合法JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("工具参数必须为对象")
        return parsed
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    raise ValueError("工具参数必须为对象")


def execute_tool(name: str, raw_args) -> str:
    started = time.monotonic()
    args = {}
    def finish(result, ok=True, flag=""):
        record(name, args, ok, int((time.monotonic() - started) * 1000), flag)
        return result

    try:
        args = _normalize_args(raw_args)
    except ValueError:
        return finish("参数缺失或无效：工具参数必须是合法JSON对象", False, "invalid_args")

    if name not in allowed_tools(current()[1].role):
        return finish("不支持的工具或无权调用。", False, "forbidden_tool")
    if set(args) & {"user_id", "shop_id", "role", "username"}:
        return finish("参数无效：不允许指定其他身份或店铺。", False, "identity_override")
    spec = SPECS.get(name)
    func = IMPL.get(name)
    if spec is None or func is None:
        return finish("不支持的工具。", False, "unknown_tool")
    try:
        parsed = spec.model_validate(args)
    except ValidationError as exc:
        error = exc.errors()[0]
        loc = ".".join(str(part) for part in error["loc"])
        detail = f"{loc}：{error['msg']}" if loc else error['msg']
        return finish(f"参数缺失或无效：{detail}", False, "invalid_args")

    if name in ("recommend_products", "clarify_recommendation") and not current()[1].catalog_loaded:
        return finish("请先调用get_store_catalog了解本店商品。", False, "catalog_required")

    for _ in range(2):
        try:
            result = str(func(**parsed.model_dump()))
            denied = result.startswith("没有找到这个订单")
            return finish(result, not denied, "order_not_found_or_denied" if denied else "")
        except HTTPException as exc:
            if 400 <= exc.status_code < 500 and exc.status_code != 429:
                return finish("没有找到本店可访问的资源。" if exc.status_code == 404 else "业务操作被拒绝，请检查参数、权限或资源状态。", False, "business_rejected")
        except Exception:
            pass
    return finish("工具执行失败，请稍后重试。", False, "execution_error")
