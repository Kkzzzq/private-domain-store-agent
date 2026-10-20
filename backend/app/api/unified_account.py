from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, decode_access_token, token_is_revoked
from app.models.account import SharedAccount
from app.models.tables import Shop, User
from app.schemas.dto import LoginIn, RegisterIn
from app.services.catalog import serialize_shop

router = APIRouter()


class SessionTokens(BaseModel):
    token_b: str = Field(default='', max_length=2048)
    token_c: str = Field(default='', max_length=2048)


def account_session(db, user, saved=None):
    # One real user owns both views. Serialize initial shop provisioning.
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    if not db.get(SharedAccount, user.id):
        db.add(SharedAccount(user_id=user.id))
    shop = db.scalar(select(Shop).where(Shop.merchant_id == user.id).with_for_update())
    if not shop:
        base = user.username.lower()
        code, suffix = base, 1
        while db.scalar(select(Shop.id).where(Shop.share_code == code)):
            suffix += 1
            code = f'{base}{suffix}'
        shop = Shop(merchant_id=user.id, name=f'{user.nickname or user.username}的小店', share_code=code, notice='', status='open')
        db.add(shop)
    db.commit()
    def view_token(role, value):
        if value:
            try:
                claims=decode_access_token(value)
                if int(claims['sub'])==user.id and claims.get('role')==role and not token_is_revoked(value):
                    return value
            except Exception:
                pass
        return create_access_token(user_id=user.id, username=user.username, role=role)
    return dict(user=dict(id=user.id, username=user.username, nickname=user.nickname, role=user.role),
        token_b=view_token('merchant',saved.token_b if saved else ''),
        token_c=view_token('customer',saved.token_c if saved else ''), shop=serialize_shop(shop))


@router.get('/demo-login')
def demo_login(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    # This is an explicitly public demo identity, configured separately from secrets.
    return dict(enabled=settings.demo_login_enabled,
        username=settings.demo_login_username if settings.demo_login_enabled else '',
        password=settings.demo_login_password if settings.demo_login_enabled else '')


@router.post('/portal-login')
def portal_login(body: LoginIn, request: Request, db: Session=Depends(get_db)):
    from app.api.auth import login
    result = login(body, request, db)
    return account_session(db, db.get(User, result.user.id))


@router.post('/portal-register')
def portal_register(body: RegisterIn, request: Request, db: Session=Depends(get_db)):
    from app.api.auth import register
    result = register(body, request, db)
    return account_session(db, db.get(User, result.user.id))


@router.post('/portal-session')
def portal_session(body: SessionTokens | None=None, user=Depends(get_current_user), db: Session=Depends(get_db)):
    return account_session(db, user, body)
