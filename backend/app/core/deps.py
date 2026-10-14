from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.tables import User

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
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="登录已失效")
    return user


def require_merchant(user: User = Depends(get_current_user)) -> User:
    if user.role != "merchant":
        raise HTTPException(status_code=403, detail="只有商家可以管理商品")
    return user


def require_customer(user: User = Depends(get_current_user)) -> User:
    if user.role != "customer":
        raise HTTPException(status_code=403, detail="请使用买家账号")
    return user


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """买家端有些接口不登录也能看，登录了才带收藏状态。"""
    if creds is None:
        return None
    try:
        payload = decode_access_token(creds.credentials)
        return db.get(User, int(payload["sub"]))
    except Exception:
        return None
