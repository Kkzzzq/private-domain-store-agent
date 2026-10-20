from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.redis_client import MemoryRedis
from test_bc_link import login


def test_password_storage_and_unicode_boundary(client):
    password = "中" * 24
    response = client.post("/api/v1/auth/register", json={"username": "unicode_user", "password": password})
    assert response.status_code == 200
    from app.db.session import SessionLocal
    from app.models.tables import User
    with SessionLocal() as db:
        user = db.get(User, response.json()["user"]["id"])
        assert user.password_hash != password
        assert verify_password(password, user.password_hash)
    assert client.post("/api/v1/auth/login", json={"username": "unicode_user", "password": password}).status_code == 200
    assert client.post("/api/v1/auth/register", json={"username": "too_long", "password": "中" * 25}).status_code == 422
    assert client.post("/api/v1/auth/login", json={"username": "unicode_user", "password": "中" * 25}).status_code == 401
    assert not verify_password("password", "malformed-hash")
    assert not verify_password(chr(0xD800), hash_password("password"))
    assert not verify_password("中" * 25, hash_password("password"))


def test_logout_revokes_only_this_token(client):
    first = login(client, "alice")
    second = login(client, "alice")
    assert first != second
    padded = {"Authorization": first["Authorization"] + "="}
    assert client.get("/api/v1/auth/me", headers=padded).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=first).json() == {"logged_out": True}
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.get("/api/v1/auth/me", headers=padded).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second).status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 401


def test_invalid_tokens_and_database_role_are_authoritative(client):
    headers = login(client, "alice")
    payload = jwt.decode(headers["Authorization"].split()[1], settings.jwt_secret, algorithms=["HS256"])
    payload["role"] = "merchant"
    signed = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    assert client.get("/api/v1/b/products", headers={"Authorization": "Bearer " + signed}).status_code == 403
    payload["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    missing_exp = jwt.encode({"sub": payload["sub"]}, settings.jwt_secret, algorithm="HS256")
    for token in [expired, missing_exp, signed + "tampered", "not-a-jwt"]:
        assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_login_and_registration_rate_limits(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_login_limit", 2)
    body = {"username": "unknown", "password": "wrong-password"}
    assert client.post("/api/v1/auth/login", json=body).status_code == 401
    assert client.post("/api/v1/auth/login", json=body).status_code == 401
    blocked = client.post("/api/v1/auth/login", json=body)
    assert blocked.status_code == 429 and blocked.headers["Retry-After"] == "60"
    monkeypatch.setattr(settings, "auth_register_limit", 1)
    body = {"username": "new_account", "password": "secret123"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 200
    body["username"] = "another_account"
    assert client.post("/api/v1/auth/register", json=body).status_code == 429


def test_registration_rejects_roles_and_duplicate_names(client):
    body = {"username": "new_account", "password": "secret123"}
    assert client.post("/api/v1/auth/register", json={**body, "role": "admin"}).status_code == 422
    assert client.post("/api/v1/auth/register", json=body).status_code == 200
    assert client.post("/api/v1/auth/register", json=body).status_code == 409


def test_memory_rate_limit_has_fixed_expiry():
    cache = MemoryRedis()
    assert cache.increment("attempt", 60) == 1
    expiry = cache.expires["attempt"]
    assert cache.increment("attempt", 60) == 2
    assert cache.expires["attempt"] == expiry


def test_registration_conflict_rolls_back(client, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session
    def conflict(session):
        raise IntegrityError("insert", {}, Exception("duplicate"))
    monkeypatch.setattr(Session, "commit", conflict)
    response = client.post("/api/v1/auth/register", json={"username": "racing_account", "password": "secret123"})
    assert response.status_code == 409
    from app.db.session import SessionLocal
    from app.models.tables import User
    from sqlalchemy import select
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.username == "racing_account")) is None


def test_revocation_store_failure_is_not_treated_as_anonymous(client, monkeypatch):
    from fastapi import HTTPException
    from app.core import deps
    headers = login(client, "alice")
    def unavailable(token):
        raise HTTPException(503, "Redis 暂时不可用")
    monkeypatch.setattr(deps, "token_is_revoked", unavailable)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 503
