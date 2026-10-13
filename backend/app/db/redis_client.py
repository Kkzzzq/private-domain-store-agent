import fnmatch
import json
from typing import Any

import redis

from app.core.config import settings
from app.core.logging import logger


class MemoryRedis:
    """进程内替代。只有 Redis 没启动，或测试显式指定 memory 时才用。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def ping(self) -> bool:
        return True

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                removed += 1
        return removed

    def keys(self, pattern: str) -> list[str]:
        return [key for key in self.store if fnmatch.fnmatch(key, pattern)]

    def flush(self) -> None:
        self.store.clear()


class RedisClient:
    """get_json / set_json / delete_pattern 与优选电商项目里的缓存接口一致。"""

    def __init__(self) -> None:
        self._client: redis.Redis | MemoryRedis | None = None
        self.using_memory = False

    def connect(self) -> None:
        if settings.redis_url == "memory":
            self._client = MemoryRedis()
            self.using_memory = True
            return
        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        try:
            client.ping()
        except redis.RedisError as exc:
            logger.warning("Redis 不可用，会话和热点缓存改用进程内存：%s", exc)
            self._client = MemoryRedis()
            self.using_memory = True
            return
        self._client = client
        self.using_memory = False

    def _ensure(self) -> redis.Redis | MemoryRedis:
        if self._client is None:
            self.connect()
        assert self._client is not None
        return self._client

    def get_json(self, key: str) -> Any:
        raw = self._ensure().get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Redis 键 %s 不是合法 JSON", key)
            return None

    def set_json(self, key: str, value: Any, ex: int | None = 3600) -> None:
        self._ensure().set(key, json.dumps(value, ensure_ascii=False), ex=ex)

    def delete_pattern(self, pattern: str) -> int:
        client = self._ensure()
        keys = client.keys(pattern)
        if not keys:
            return 0
        return int(client.delete(*keys))

    def flush(self) -> None:
        client = self._ensure()
        if isinstance(client, MemoryRedis):
            client.flush()


_redis = RedisClient()


def get_redis() -> RedisClient:
    if _redis._client is None:
        _redis.connect()
    return _redis
