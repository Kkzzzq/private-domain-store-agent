import argparse
import os
from pathlib import Path
import subprocess
import sys
from threading import Timer
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description="临时OP质量UI验收；独立数据及worker")
    parser.add_argument("--seconds", type=int, default=900, choices=range(60, 1801))
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    database = backend / "data" / "acceptance" / f"quality-ui-{uuid4().hex}.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    os.environ.update(DATABASE_URL="sqlite:///" + database.as_posix(), REDIS_URL="memory", STRICT_DEPENDENCIES="false",
                      AGENT_MODE="fallback", AGENT_REQUIRE_LLM="false", RAG_REQUIRE_VECTORS="false",
                      JWT_SECRET=uuid4().hex + uuid4().hex)
    sys.path.insert(0, str(backend))
    from sqlalchemy import select
    from app.main import app, init_db
    from app.db.session import SessionLocal
    from app.models.tables import User
    from app.models.operations import Operator
    from app.models.quality import QualityGrant
    from app.quality.catalog import CAPABILITIES
    from app.seed import seed_if_empty
    import uvicorn
    init_db()
    with SessionLocal() as db:
        seed_if_empty(db)
        user = db.scalar(select(User).where(User.username == "merchant"))
        db.add(Operator(user_id=user.id))
        db.add(QualityGrant(user_id=user.id, capabilities=sorted(CAPABILITIES)))
        db.commit()
    worker = subprocess.Popen([sys.executable, "-m", "app.quality.worker"], cwd=backend,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18129, log_level="warning"))
    timer = Timer(args.seconds, lambda: setattr(server, "should_exit", True))
    timer.daemon = True
    timer.start()
    try:
        server.run()
    finally:
        timer.cancel()
        from app.quality.worker import stop_process
        stop_process(worker)


if __name__ == "__main__":
    main()
