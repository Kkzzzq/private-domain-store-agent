import argparse
import os
import sys
from pathlib import Path
from threading import Timer
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description="临时UI验收服务，独立SQLite和内存Redis，绝不连接实际商家库")
    parser.add_argument("--seconds", type=int, default=300, choices=range(30, 601))
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    database = backend / "data" / "acceptance" / f"ui-audit-{uuid4().hex}.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    os.environ.update(DATABASE_URL=f"sqlite:///{database.as_posix()}", REDIS_URL="memory",
                      AGENT_MODE="fallback", STRICT_DEPENDENCIES="false", AGENT_REQUIRE_LLM="false",
                      RAG_REQUIRE_VECTORS="false", JWT_SECRET=uuid4().hex + uuid4().hex)
    sys.path.insert(0, str(backend))
    import uvicorn
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=18009, log_level="warning"))
    def finish():
        server.should_exit = True
    timer = Timer(args.seconds, finish)
    timer.daemon = True
    timer.start()
    try:
        server.run()
    finally:
        timer.cancel()


if __name__ == "__main__":
    main()
