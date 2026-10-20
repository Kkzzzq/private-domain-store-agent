import json
from uuid import uuid4

from app.db.redis_client import MemoryRedis, get_redis


def push(kind, value):
    key = "qa:queue:" + kind
    def operation(client):
        if not isinstance(client, MemoryRedis):
            return client.lpush(key, value)
        with client.lock:
            values = json.loads(client.get(key) or "[]")
            values.insert(0, value)
            client.set(key, json.dumps(values), ex=86400)
    get_redis()._perform(operation)


def pop(kind):
    key = "qa:queue:" + kind
    def operation(client):
        if not isinstance(client, MemoryRedis):
            return client.rpop(key)
        with client.lock:
            values = json.loads(client.get(key) or "[]")
            value = values.pop() if values else None
            client.set(key, json.dumps(values), ex=86400)
            return value
    return get_redis()._perform(operation)


def acquire(kind):
    token = uuid4().hex
    key = "qa:lane:" + kind
    def operation(client):
        if not isinstance(client, MemoryRedis):
            return bool(client.set(key, token, ex=110, nx=True))
        with client.lock:
            if client.get(key):
                return False
            client.set(key, token, ex=110)
            return True
    return token if get_redis()._perform(operation) else None


def release(kind, token):
    key = "qa:lane:" + kind
    def operation(client):
        if not isinstance(client, MemoryRedis):
            return client.eval("if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end; return 0", 1, key, token)
        with client.lock:
            return client.delete(key) if client.get(key) == token else 0
    get_redis()._perform(operation)


def renew(kind, token):
    key = "qa:lane:" + kind
    def operation(client):
        if not isinstance(client, MemoryRedis):
            return client.eval("if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('EXPIRE',KEYS[1],110) end; return 0", 1, key, token)
        with client.lock:
            if client.get(key) != token:
                return False
            client.set(key, token, ex=110)
            return True
    return bool(get_redis()._perform(operation))
