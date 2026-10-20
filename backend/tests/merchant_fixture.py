"""Explicit authorized merchant setup for cross-shop tests, never public registration."""
import json
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.tables import User, Shop
from app.models.account import MerchantAccess
from app.api.unified_account import account_session

def authorize_merchant(client, response=None, username=None):
    data = response if isinstance(response, dict) else response.json() if response is not None else None
    with SessionLocal() as db:
        user = db.get(User,data['user']['id']) if data else db.scalar(select(User).where(User.username==username))
        user.role = 'merchant'  # explicit existing merchant fixture
        db.add(MerchantAccess(user_id=user.id)); db.commit()
        session = account_session(db,user)
        db.get(Shop,session['shop']['id']).name=user.nickname
        db.commit()
    if data:
        data['access_token'] = session['token_b']
        data['user']['role'] = 'merchant'
        if not isinstance(response,dict): response._content=json.dumps(data).encode()
