from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, token_is_revoked
from app.db.session import SessionLocal
from app.models.tables import User, AccountClosure
from app.models.account import SharedAccount, can_manage_store
from app.services.governance import account_allowed

bearer = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="登录已失效") from exc
    if token_is_revoked(creds.credentials):
        raise HTTPException(status_code=401, detail="登录已失效")
    user = db.get(User, user_id)
    if user is None or db.get(AccountClosure, user_id) or not account_allowed(db, user, payload):
        raise HTTPException(status_code=401, detail="登录已失效")
    if db.get(SharedAccount, user_id) and payload.get('role') in ('customer', 'merchant'):
        user._actor_role = 'customer' if payload['role'] == 'merchant' and not can_manage_store(db, user) else payload['role']
    if user.actor_role == 'merchant' and not can_manage_store(db, user):
        user._actor_role = 'customer'
    return user


def require_merchant(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if user.actor_role != "merchant" or not can_manage_store(db, user):
        raise HTTPException(status_code=403, detail="只有商家可以管理商品")
    return user


def require_customer(user: User = Depends(get_current_user)) -> User:
    if user.actor_role != "customer":
        raise HTTPException(status_code=403, detail="请使用买家账号")
    return user


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """买家端有些接口不登录也能看。"""
    if creds is None:
        return None
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except Exception:
        return None
    if token_is_revoked(creds.credentials) or db.get(AccountClosure, user_id):
        return None
    user = db.get(User, user_id)
    if user and not account_allowed(db, user, payload):
        return None
    if user and db.get(SharedAccount, user_id) and payload.get('role') in ('customer', 'merchant'):
        user._actor_role = 'customer' if payload['role'] == 'merchant' and not can_manage_store(db, user) else payload['role']
    if user and user.actor_role == 'merchant' and not can_manage_store(db, user):
        user._actor_role = 'customer'
    return user
