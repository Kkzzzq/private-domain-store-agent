import json
import os
import re
from urllib.parse import quote
from uuid import uuid4


class NamespacedRedis:
    def __init__(self, raw, prefix):
        if not re.fullmatch(r"qa:[a-f0-9]{32}:", prefix):
            raise RuntimeError("无效的测试Redis命名空间")
        self.raw, self.prefix = raw, prefix

    def ping(self):
        return self.raw.ping()

    def get(self, key):
        return self.raw.get(self.prefix + key)

    def set(self, key, value, **kwargs):
        return self.raw.set(self.prefix + key, value, **kwargs)

    def delete(self, *keys):
        return self.raw.delete(*(self.prefix + key for key in keys)) if keys else 0

    def scan_iter(self, match="*", **kwargs):
        for key in self.raw.scan_iter(match=self.prefix + match, **kwargs):
            if not key.startswith(self.prefix):
                raise RuntimeError("Redis返回了命名空间外的键")
            yield key[len(self.prefix):]

    def eval(self, script, numkeys, *args):
        return self.raw.eval(script, numkeys, *(self.prefix + key for key in args[:numkeys]), *args[numkeys:])


def install_namespace():
    prefix = os.environ.get("QA_NATIVE_PREFIX")
    if not prefix:
        return
    from app.db.redis_client import get_redis
    cache = get_redis()
    if cache.using_memory:
        raise RuntimeError("原生测试禁止内存Redis")
    cache._client = NamespacedRedis(cache._client, prefix)


class NativeWorkspace:
    def __init__(self):
        self.identifier = uuid4().hex
        self.database = "qa_" + self.identifier
        self.username = "qa_" + self.identifier[:24]
        self.password = uuid4().hex
        self.prefix = "qa:" + self.identifier + ":"
        self.database_created = False
        self.user_created = False
        self.connection = None
        self.redis = None

    def prepare(self):
        import pymysql
        import redis
        from app.core.config import settings
        from scripts import native_services
        if not settings.qa_native_enabled or not settings.qa_native_mysql_password:
            raise RuntimeError("原生测试档未授权配置")
        state = json.loads(native_services.STATE.read_text(encoding="utf-8"))
        record = state.get("mysql")
        if not record or not native_services.owned_process(record, native_services.process_info(record["pid"])) or not native_services.owns_port(record, 13306):
            raise RuntimeError("无法证明本地原生MySQL归属，拒绝创建测试库")
        self.connection = pymysql.connect(host="127.0.0.1", port=13306, user="root", password=settings.qa_native_mysql_password, autocommit=True)
        self.redis = redis.Redis(host="127.0.0.1", port=16379, decode_responses=True, socket_timeout=3)
        self.redis.ping()
        with self.connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{self.database}` CHARACTER SET utf8mb4")
            self.database_created = True
            cursor.execute("CREATE USER %s@'127.0.0.1' IDENTIFIED BY %s", (self.username, self.password))
            self.user_created = True
            cursor.execute(f"GRANT ALL ON `{self.database}`.* TO %s@'127.0.0.1'", (self.username,))
        return {"QA_NATIVE_DATABASE_URL": f"mysql+pymysql://{self.username}:{quote(self.password)}@127.0.0.1:13306/{self.database}",
                "QA_NATIVE_PREFIX": self.prefix}

    def close(self):
        errors = []
        if not re.fullmatch(r"qa_[a-f0-9]{32}", self.database) or not re.fullmatch(r"qa_[a-f0-9]{24}", self.username):
            raise RuntimeError("测试资源标识无效，拒绝清理")
        if self.redis:
            try:
                keys = list(self.redis.scan_iter(match=self.prefix + "*"))
                if any(not key.startswith(self.prefix) for key in keys):
                    raise RuntimeError("清理超出命名空间")
                if keys:
                    self.redis.delete(*keys)
                if list(self.redis.scan_iter(match=self.prefix + "*")):
                    raise RuntimeError("Redis清理后仍有测试键")
            except Exception:
                errors.append("Redis测试命名空间未清理")
        if self.connection:
            try:
                with self.connection.cursor() as cursor:
                    if self.database_created:
                        cursor.execute(f"DROP DATABASE `{self.database}`")
                    if self.user_created:
                        cursor.execute("DROP USER %s@'127.0.0.1'", (self.username,))
            except Exception:
                errors.append("MySQL测试库或测试用户未清理")
            finally:
                self.connection.close()
        if errors:
            raise RuntimeError("；".join(errors))
