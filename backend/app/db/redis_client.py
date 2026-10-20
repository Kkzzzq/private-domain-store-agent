import fnmatch
import json
import time
from threading import Lock
from typing import Any

import redis

from app.core.config import settings
from app.core.logging import logger


class MemoryRedis:
    """进程内替代。只有 Redis 没启动，或测试显式指定 memory 时才用。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.expires: dict[str, float] = {}
        self.lock = Lock()

    def ping(self) -> bool:
        return True

    def get(self, key: str) -> str | None:
        if self.expires.get(key, float("inf")) <= time.monotonic():
            self.delete(key)
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        if ex is not None:
            self.expires[key] = time.monotonic() + ex
        else:
            self.expires.pop(key, None)

    def increment(self, key, ttl):
        with self.lock:
            count = int(self.get(key) or 0) + 1
            self.set(key, str(count), ex=ttl)
            return count

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                self.expires.pop(key, None)
                removed += 1
        return removed

    def keys(self, pattern: str) -> list[str]:
        return [key for key in self.store if fnmatch.fnmatch(key, pattern)]

    def flush(self) -> None:
        self.store.clear()
        self.expires.clear()


class RedisClient:
    """get_json / set_json / delete_pattern 与优选电商项目里的缓存接口一致。"""

    def __init__(self) -> None:
        self._client: redis.Redis | MemoryRedis | None = None
        self.using_memory = False

    def connect(self) -> None:
        if settings.redis_url == "memory":
            if settings.strict_dependencies:
                raise RuntimeError("严格模式要求真实 Redis")
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
            if settings.strict_dependencies:
                raise RuntimeError("严格模式 Redis 不可用") from exc
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

    def verify(self) -> bool:
        client = self._ensure()
        if settings.strict_dependencies and isinstance(client, MemoryRedis):
            raise RuntimeError("严格模式不允许内存 Redis")
        return bool(client.ping())

    def _perform(self, operation):
        try:
            return operation(self._ensure())
        except redis.RedisError as exc:
            if settings.strict_dependencies:
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail="Redis 暂时不可用") from exc
            logger.warning("Redis 运行中断连，切换进程内存")
            self._client = MemoryRedis()
            self.using_memory = True
            return operation(self._client)

    def get_json(self, key: str) -> Any:
        raw = self._perform(lambda client: client.get(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Redis 键 %s 不是合法 JSON", key)
            return None

    def increment(self, key, ttl):
        def increment_client(client):
            if isinstance(client, MemoryRedis):
                return client.increment(key, ttl)
            return int(client.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n", 1, key, ttl))
        return self._perform(increment_client)

    def set_json(self, key: str, value: Any, ex: int | None = 3600) -> None:
        self._perform(lambda client: client.set(key, json.dumps(value, ensure_ascii=False), ex=ex))

    def delete_pattern(self, pattern: str) -> int:
        def delete_matching(client):
            keys = client.keys(pattern) if isinstance(client, MemoryRedis) else list(client.scan_iter(match=pattern))
            return int(client.delete(*keys)) if keys else 0
        return self._perform(delete_matching)

    def flush(self) -> None:
        client = self._ensure()
        if isinstance(client, MemoryRedis):
            client.flush()


_redis = RedisClient()


def get_redis() -> RedisClient:
    if _redis._client is None:
        _redis.connect()
    return _redis
