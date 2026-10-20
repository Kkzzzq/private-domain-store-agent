import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    from app.quality.native import install_namespace
    install_namespace()
    worker = None
    if os.environ.get("QA_BROWSER_OP") == "1":
        from app.main import init_db
        from app.db.session import SessionLocal
        from app.seed import seed_if_empty
        from app.models.tables import User
        from app.models.operations import Operator
        from app.models.quality import QualityGrant
        from app.quality.catalog import CAPABILITIES
        from sqlalchemy import select
        init_db()
        with SessionLocal() as db:
            seed_if_empty(db)
            user = db.scalar(select(User).where(User.username == "merchant"))
            db.add(Operator(user_id=user.id))
            db.add(QualityGrant(user_id=user.id, capabilities=sorted(CAPABILITIES)))
            db.commit()
        worker = subprocess.Popen([sys.executable, "-m", "app.quality.worker"], creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    import uvicorn
    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        if worker:
            from app.quality.worker import stop_process
            stop_process(worker)


if __name__ == "__main__":
    main()
