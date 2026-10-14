import json

from app.agent.context import current
from app.core.logging import logger
from app.models.tables import AgentToolLog


def record(name, args, ok, latency_ms, flag):
    try:
        db, actor = current()
        safe = {key: value for key, value in args.items() if key in ("sku_id", "product_id", "reason", "limit", "threshold", "budget_yuan")}
        if args.get("order_no"):
            safe["order_no"] = "***" + str(args["order_no"])[-4:]
        with db.begin_nested():
            db.add(AgentToolLog(user_id=actor.user_id, shop_id=actor.shop_id, session_id=actor.session_id,
                                tool=name[:64], args=json.dumps(safe), ok=ok, latency_ms=latency_ms, flag=flag))
        db.commit()
    except Exception:
        logger.warning("工具审计暂时不可用")
