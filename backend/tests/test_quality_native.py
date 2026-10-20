import pytest
from pydantic import ValidationError

from app.quality.native import NamespacedRedis
from app.quality.service import PlanIn
from app.core.config import settings


def test_native_profile_requires_server_authorization(monkeypatch):
    monkeypatch.setattr(settings, "qa_native_enabled", False)
    with pytest.raises(ValidationError, match="授权"):
        PlanIn(goal="原生依赖验证", kind="functional", case_ids=["F01"], environment_id="native-local")
    monkeypatch.setattr(settings, "qa_native_enabled", True)
    assert PlanIn(goal="原生依赖验证", kind="functional", case_ids=["F01"], environment_id="native-local")


def test_native_redis_never_accesses_or_deletes_foreign_keys():
    prefix = "qa:" + "a" * 32 + ":"
    calls = []
    class Raw:
        def set(self, *args, **kwargs): calls.append(("set", args))
        def get(self, key): calls.append(("get", key))
        def delete(self, *args): calls.append(("delete", args))
        def eval(self, *args): calls.append(("eval", args))
        def scan_iter(self, match, **kwargs):
            calls.append(("scan", match))
            yield prefix + "session"
    cache = NamespacedRedis(Raw(), prefix)
    cache.set("session", "value");cache.get("session")
    cache.eval("lua", 1, "rate", 60)
    cache.delete(*list(cache.scan_iter("*")))
    assert calls == [("set", (prefix + "session", "value")), ("get", prefix + "session"),
                     ("eval", ("lua", 1, prefix + "rate", 60)), ("scan", prefix + "*"), ("delete", (prefix + "session",))]
    with pytest.raises(RuntimeError, match="命名空间"):
        NamespacedRedis(Raw(), "*")


def test_native_redis_rejects_unexpected_scan_result():
    class Raw:
        def scan_iter(self, **kwargs): yield "session:actual-buyer"
    cache = NamespacedRedis(Raw(), "qa:" + "a" * 32 + ":")
    with pytest.raises(RuntimeError, match="命名空间外"):
        list(cache.scan_iter())
