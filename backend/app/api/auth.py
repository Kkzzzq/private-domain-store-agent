from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.tables import Shop, User, AccountClosure, Order
from pydantic import BaseModel, Field
from app.schemas.dto import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role, nickname=user.nickname)


def _share_code(db: Session, username: str) -> str:
    base = username.lower()
    code = base
    number = 1
    while db.scalar(select(Shop).where(Shop.share_code == code)):
        number += 1
        code = f"{base}{number}"
    return code


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(User.username == body.username))
    if exists is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        nickname=body.nickname.strip() or body.username,
    )
    db.add(user)
    db.flush()
    if user.role == "merchant":
        db.add(
            Shop(
                merchant_id=user.id,
                name=user.nickname,
                notice="",
                share_code=_share_code(db, user.username),
                status="open",
            )
        )
    db.commit()
    db.refresh(user)
    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return TokenOut(access_token=token, user=_user_out(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash) or db.get(AccountClosure, user.id):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return TokenOut(access_token=token, user=_user_out(user))


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
    db.refresh(user, with_for_update=True)
    if body.confirmation != "注销账号" or not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "请检查当前密码，并输入“注销账号”确认")
    shops = db.scalars(select(Shop).where(Shop.merchant_id == user.id).with_for_update()).all()
    unfinished = select(Order.id).where(Order.status.in_(["pending", "paid", "shipped"]))
    unfinished = unfinished.where(Order.shop_id.in_([shop.id for shop in shops])) if user.role == "merchant" else unfinished.where(Order.user_id == user.id)
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
