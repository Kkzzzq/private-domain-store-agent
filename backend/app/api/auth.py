from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import bearer, get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password, revoke_access_token
from app.db.redis_client import get_redis
from app.models.tables import Shop, User, AccountClosure, Order
from pydantic import BaseModel, Field
from app.schemas.dto import LoginIn, RegisterIn, TokenOut, UserOut
from app.services.governance import account_allowed

router = APIRouter(prefix="/auth", tags=["auth"])
_dummy_password_hash = hash_password("not-a-real-account-password")


def _limit_attempts(request: Request, action: str, limit: int, seconds: int) -> None:
    address = request.client.host if request.client else "unknown"
    key = "auth:attempt:" + action + ":" + sha256(address.encode()).hexdigest()
    if get_redis().increment(key, seconds) > limit:
        raise HTTPException(429, "操作过于频繁，请稍后重试", headers={"Retry-After": str(seconds)})


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.actor_role, nickname=user.nickname)


def _share_code(db: Session, username: str) -> str:
    base = username.lower()
    code = base
    number = 1
    while db.scalar(select(Shop).where(Shop.share_code == code)):
        number += 1
        code = f"{base}{number}"
    return code


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    _limit_attempts(request, "register", settings.auth_register_limit, 900)
    exists = db.scalar(select(User).where(User.username == body.username))
    if exists is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role="customer",
        nickname=body.nickname.strip() or body.username,
    )
    db.add(user)
    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "账号信息冲突，请更换用户名后重试") from exc
    db.refresh(user)
    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return TokenOut(access_token=token, user=_user_out(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    _limit_attempts(request, "login", settings.auth_login_limit, 60)
    user = db.scalar(select(User).where(User.username == body.username))
    valid = verify_password(body.password, user.password_hash if user else _dummy_password_hash)
    if user is None or not valid or db.get(AccountClosure, user.id) or not account_allowed(db, user):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return TokenOut(access_token=token, user=_user_out(user))


@router.post("/logout")
def logout(user: User = Depends(get_current_user), creds: HTTPAuthorizationCredentials = Depends(bearer)):
    revoke_access_token(creds.credentials)
    return {"logged_out": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


class ProfileIn(BaseModel):
    nickname: str = Field(min_length=1, max_length=32)


class CloseAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=64)
    confirmation: str


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    nickname = body.nickname.strip()
    if not nickname:
        raise HTTPException(422, "昵称不能为空")
    user.nickname = nickname
    db.commit()
    return _user_out(user)


@router.post("/me/close")
def close_me(body: CloseAccountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.operations import Operator
    if db.get(Operator,user.id):
        raise HTTPException(409,'平台运营账号请先移交平台权限，再注销账号')
    db.refresh(user, with_for_update=True)
    if body.confirmation != "注销账号" or not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "请检查当前密码，并输入“注销账号”确认")
    shops = db.scalars(select(Shop).where(Shop.merchant_id == user.id).with_for_update()).all()
    unfinished = select(Order.id).where(Order.status.in_(["pending", "paid", "shipped"]))
    unfinished = unfinished.where(or_(Order.user_id == user.id, Order.shop_id.in_([shop.id for shop in shops])))
    if db.scalar(unfinished.limit(1)):
        raise HTTPException(409, "存在未完成订单，请先处理后再注销")
    for shop in shops:
        shop.status = "closed"
    if not db.get(AccountClosure, user.id):
        db.add(AccountClosure(user_id=user.id))
    db.commit()
    from app.services.catalog import invalidate_catalog_cache
    invalidate_catalog_cache()
    return {"closed": True}


from app.api.unified_account import router as unified_router
router.include_router(unified_router)
