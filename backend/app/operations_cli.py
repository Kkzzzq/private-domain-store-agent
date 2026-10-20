"""Run from backend: python scripts/manage_operator.py USERNAME [--revoke]."""
import argparse
from sqlalchemy import select
from app.db.session import SessionLocal, engine
from app.models.tables import User
from app.models.operations import Operator, OperationLog


def main():
    parser = argparse.ArgumentParser(description='授予或撤销现有账号的平台运营权限，不改变B/C身份或密码')
    parser.add_argument('username')
    parser.add_argument('--revoke', action='store_true')
    args = parser.parse_args()
    Operator.__table__.create(engine, checkfirst=True)
    OperationLog.__table__.create(engine, checkfirst=True)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if user is None:
            raise SystemExit('账号不存在，请先通过正常注册创建专用运营账号')
        record = db.get(Operator, user.id)
        if args.revoke and record:
            db.delete(record)
        elif not args.revoke and not record:
            db.add(Operator(user_id=user.id))
        db.commit()
        print('运营权限已撤销' if args.revoke else '运营权限已授予')


if __name__ == '__main__':
    main()

