import time

from fastapi import HTTPException

from app.core.config import settings
from app.db.redis_client import get_redis


def check_rate(user_id):
    limit = settings.agent_rate_limit_per_minute
    if limit <= 0:
        return
    count = get_redis().increment(f"agent-rate:{user_id}:{int(time.time() // 60)}", 65)
    if count > limit:
        raise HTTPException(status_code=429, detail="提问过于频繁，请稍后重试", headers={"Retry-After": "60"})
