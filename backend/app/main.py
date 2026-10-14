import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from app.api.router import router
from app.core.logging import logger
from app.db.base import Base
from app.db.session import SessionLocal, engine


def init_db() -> None:
    import app.models.tables  # noqa: F401

    last_error: Exception | None = None
    for _ in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            _ensure_sqlite_columns()
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(1)
    raise last_error or RuntimeError("数据库初始化失败")


def _ensure_sqlite_columns() -> None:
    from app.core.config import settings

    if not str(settings.database_url).startswith("sqlite"):
        return
    needed = {
        "products": {
            "image_url": "VARCHAR(500) DEFAULT ''",
            "sort_order": "INTEGER DEFAULT 0",
            "sales_count": "INTEGER DEFAULT 0",
        },
        "orders": {
            "freight_cents": "INTEGER DEFAULT 0",
            "receiver": "VARCHAR(32) DEFAULT ''",
            "phone": "VARCHAR(20) DEFAULT ''",
        },
    }
    with engine.begin() as conn:
        for table, columns in needed.items():
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            if not rows:
                continue
            existing = {row[1] for row in rows}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    init_db()
    from app.seed import seed_if_empty, upgrade_demo

    db = SessionLocal()
    try:
        seed_if_empty(db)
        upgrade_demo(db)
    finally:
        db.close()
    logger.info("私域店铺已启动")
    yield


app = FastAPI(title="私域电商智能运营平台", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/v1")

from app.core.config import settings

if settings.web_dir.exists():
    app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
