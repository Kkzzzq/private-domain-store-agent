import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from app.api.router import router
from app.core.config import settings
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
    """本地演示库不加迁移工具，启动时补齐新加的列。"""
    if not str(settings.database_url).startswith("sqlite"):
        return
    needed = {
        "products": {
            "image_url": "VARCHAR(500) DEFAULT ''",
            "sort_order": "INTEGER DEFAULT 0",
            "sales_count": "INTEGER DEFAULT 0",
            "limit_per_user": "INTEGER DEFAULT 0",
        },
        "orders": {
            "freight_cents": "INTEGER DEFAULT 0",
            "receiver": "VARCHAR(32) DEFAULT ''",
            "phone": "VARCHAR(20) DEFAULT ''",
            "expires_at": "DATETIME",
        },
        "shops": {
            "logo_url": "VARCHAR(500) DEFAULT ''",
            "theme_color": "VARCHAR(16) DEFAULT '#ff5000'",
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


def _sweep_expired_orders() -> None:
    from app.services.orders import auto_cancel_expired

    db = SessionLocal()
    try:
        count = auto_cancel_expired(db)
        if count:
            logger.info("已自动取消 %s 个超时未支付订单", count)
    except Exception as exc:  # 定时任务不能把进程带崩
        logger.warning("清理超时订单失败：%s", exc)
    finally:
        db.close()


def _start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(_sweep_expired_orders, "interval", seconds=60, id="cancel_expired_orders")
    scheduler.start()
    return scheduler


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
    scheduler = None
    try:
        scheduler = _start_scheduler()
    except Exception as exc:
        logger.warning("定时任务没起来，超时订单改由接口触发清理：%s", exc)
    logger.info("私域店铺已启动")
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="私域电商智能运营平台", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/v1")

if settings.web_dir.exists():
    app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
