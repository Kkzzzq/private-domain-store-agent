import argparse

from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models.operations import Operator
from app.models.quality import QualityGrant, QualityPlan, QualityResult, QualityRun
from app.models.tables import User
from app.quality.catalog import CAPABILITIES


def main():
    parser = argparse.ArgumentParser(description="显式授权既有OP账号质量能力，不创建账号或变更B/C权限")
    parser.add_argument("username", nargs="?", help="账号名；配合 --all-operators 时可省略")
    parser.add_argument("--all-operators", action="store_true", help="给所有已授权OP账号补齐全部质量能力（平台运营＝平台管理员）")
    parser.add_argument("--revoke", action="store_true")
    parser.add_argument("--capabilities", default=",".join(sorted(CAPABILITIES)))
    args = parser.parse_args()
    if not args.username and not args.all_operators:
        raise SystemExit("请提供账号名，或使用 --all-operators")
    granted = set(args.capabilities.split(","))
    if not granted.issubset(CAPABILITIES):
        raise SystemExit("包含未知质量能力")
    for table in (QualityGrant, QualityPlan, QualityRun, QualityResult):
        table.__table__.create(engine, checkfirst=True)
    with SessionLocal() as db:
        if args.all_operators:
            from app.quality.service import provision_operators

            count = provision_operators(db)
            print(f"已为 {count} 个平台运营账号补齐全部质量能力")
            return
        user = db.scalar(select(User).where(User.username == args.username))
        if not user or not db.get(Operator, user.id):
            raise SystemExit("账号不存在或不是已授权OP；不会自动提升普通账号权限")
        record = db.get(QualityGrant, user.id)
        if args.revoke:
            if record:
                db.delete(record)
        elif record:
            record.capabilities = sorted(granted)
        else:
            db.add(QualityGrant(user_id=user.id, capabilities=sorted(granted)))
        db.commit()
    print("质量权限已撤销" if args.revoke else "质量能力已按显式范围授权")


if __name__ == "__main__":
    main()
