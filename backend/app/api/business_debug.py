from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.api.quality import quality_user
from app.core.deps import get_db
from app.db.redis_client import get_redis
from app.quality import queue, service
from app.quality.business_debug import DebugIn

router = APIRouter(prefix="/op/qa/business-debug", tags=["OP business debug"])


@router.get("")
def history(user=Depends(quality_user)):
    return get_redis().get_json(f"qa:business-debug:{user.id}") or []


@router.post("")
def debug_dialogue(body: DebugIn, user=Depends(quality_user), db=Depends(get_db)):
    service.require_execution(db, user.id, "assistant")
    if get_redis().increment(f"qa:business-debug-rate:{user.id}", 60) > 6:
        raise HTTPException(429, "调试过于频繁，请稍后重试")
    token = queue.acquire("business-debug")
    if not token:
        raise HTTPException(409, "已有合成对话在执行，请稍后重试")
    try:
        from app.quality.worker import subprocess_job
        from app.quality.sandbox import safe
        def cancelled():
            db.rollback()
            caps = service.capabilities(db, user.id)
            return "qa.assistant.run" not in caps or "qa.view" not in caps
        output = subprocess_job({"case_id": "__business_debug__", "mode": "live", "environment_id": "isolated-local",
                                 "dialogue": body.model_dump(), "max_calls": 20, "max_tokens": 60000, "timeout_seconds": 90},
                                cancelled)
        chats = [row for row in output.get("requests", []) if str(row.get("path", "")).endswith("/chat")]
        complete = (output.get("status") == "passed" and output.get("cleanup_ok")
                    and output.get("budget", {}).get("calls", 0) > 0 and len(chats) == len(body.messages)
                    and all(row.get("status") == 200 and row.get("output", {}).get("mode") == "llm" for row in chats)
                    and not cancelled())
        if not complete and not output.get("error"):
            output["error"] = "缺少完整真实模型对话或隔离清理证据，未标记完成"
        record = {"id": uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(), "role": body.role,
                  "messages": safe(body.messages), "status": "completed" if complete else "blocked", "evidence": output}
        cache = get_redis()
        key = f"qa:business-debug:{user.id}"
        cache.set_json(key, [record, *(cache.get_json(key) or [])][:10], ex=604800)
        return record
    finally:
        queue.release("business-debug", token)
