"""Explicit shop authorization: run from backend; never exposed to public registration."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.main import init_db
from app.models.tables import User
from app.models.account import MerchantAccess

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('username')
    parser.add_argument('--revoke', action='store_true')
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if not user: raise SystemExit('Account does not exist')
        access = db.get(MerchantAccess, user.id)
        if not access:
            access = MerchantAccess(user_id=user.id);db.add(access)
        access.enabled = not args.revoke
        db.commit()
    print('Store permission updated')
