from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    if len(password.encode()) > 72:
        raise ValueError("密码的 UTF-8 编码不能超过72字节")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        encoded_password = password.encode()
        if len(encoded_password) > 72:
            return False
        return bcrypt.checkpw(encoded_password, password_hash.encode())
    except (ValueError, TypeError):
        return False


def create_access_token(*, user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "username": username, "role": role, "exp": expire,
               "iat": datetime.now(timezone.utc), "issued_at_us": int(datetime.now(timezone.utc).timestamp() * 1_000_000), "jti": uuid4().hex}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["sub", "exp"]})


def revoked_token_key(token: str) -> str:
    return "auth:revoked:" + sha256(token.rsplit(".", 1)[0].encode()).hexdigest()


def token_is_revoked(token: str) -> bool:
    from app.db.redis_client import get_redis
    return bool(get_redis().get_json(revoked_token_key(token)))


def revoke_access_token(token: str) -> None:
    from app.db.redis_client import get_redis
    payload = decode_access_token(token)
    ttl = max(1, int(payload["exp"] - datetime.now(timezone.utc).timestamp()) + 1)
    get_redis().set_json(revoked_token_key(token), True, ex=ttl)
