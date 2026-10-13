from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.tables import Shop, User
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
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return TokenOut(access_token=token, user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)
