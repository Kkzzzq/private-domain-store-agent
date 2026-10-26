import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app.api.router import router
from app.core.config import settings
from app.core.logging import logger
from app.db.base import Base
from app.db.session import SessionLocal, engine


def init_db() -> None:
    import app.models.tables  # noqa: F401
    if settings.strict_dependencies and engine.dialect.name != "mysql":
        raise RuntimeError("严格依赖模式要求 MySQL")

    last_error: Exception | None = None
    for _ in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            _ensure_sqlite_columns()
            _ensure_sku_sort_order()
            _ensure_governance_columns()
            _ensure_catalog_schema()
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(1)
    raise last_error or RuntimeError("数据库初始化失败")


def _ensure_catalog_schema() -> None:
    """SPU / SKU / C 端宽表的结构升级。

    SPU 补业务编号与更新时间；SKU 的外键列由 product_id 改名为 spu_id，直接改名
    而不是新建表，订单与评价里已有的引用保持有效；宽表由 create_all 建表。
    老数据在这里就地回填，启动即可用。
    """
    inspector = inspect(engine)
    if "products" not in set(inspector.get_table_names()):
        return
    product_columns = {column["name"] for column in inspector.get_columns("products")}
    sku_columns = {column["name"] for column in inspector.get_columns("skus")}
    with engine.begin() as connection:
        if "spu_id" not in sku_columns and "product_id" in sku_columns:
            connection.exec_driver_sql("ALTER TABLE skus RENAME COLUMN product_id TO spu_id")
        if "spu_id" not in product_columns:
            connection.exec_driver_sql("ALTER TABLE products ADD COLUMN spu_id VARCHAR(32) NOT NULL DEFAULT ''")
        if "updated_at" not in product_columns:
            connection.exec_driver_sql("ALTER TABLE products ADD COLUMN updated_at DATETIME")
            connection.exec_driver_sql("UPDATE products SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
        if "updated_at" not in sku_columns:
            connection.exec_driver_sql("ALTER TABLE skus ADD COLUMN updated_at DATETIME")
            connection.exec_driver_sql("UPDATE skus SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
    _backfill_spu_numbers()
    _ensure_spu_number_index()


def _backfill_spu_numbers() -> None:
    from sqlalchemy import text

    from app.models.tables import generate_spu_id

    with engine.begin() as connection:
        rows = connection.execute(text("SELECT id FROM products WHERE spu_id IS NULL OR spu_id = ''")).fetchall()
        for (product_id,) in rows:
            connection.execute(
                text("UPDATE products SET spu_id = :spu WHERE id = :id"),
                {"spu": generate_spu_id(), "id": product_id},
            )


def _ensure_spu_number_index() -> None:
    if "ix_products_spu_id" in {index["name"] for index in inspect(engine).get_indexes("products")}:
        return
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE UNIQUE INDEX ix_products_spu_id ON products (spu_id)")
    except OperationalError:
        if "ix_products_spu_id" not in {index["name"] for index in inspect(engine).get_indexes("products")}:
            raise


def _rebuild_c_projection() -> None:
    """C 端宽表启动重建一次，首屏读取不用等自愈。"""
    from app.services.c_projection import rebuild_all

    db = SessionLocal()
    try:
        shops = rebuild_all(db)
        logger.info("C 端商品宽表已重建，覆盖 %s 家店铺", shops)
    except Exception as exc:  # 读路径还有指纹自愈兜底，不让启动失败
        logger.warning("C 端宽表重建失败，读路径将按指纹自愈：%s", exc)
    finally:
        db.close()


def _ensure_sku_sort_order() -> None:
    if "sort_order" in {column["name"] for column in inspect(engine).get_columns("skus")}:
        return
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE skus ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
    except OperationalError:
        if "sort_order" not in {column["name"] for column in inspect(engine).get_columns("skus")}:
            raise


def _ensure_governance_columns() -> None:
    if 'platform_account_restrictions' not in inspect(engine).get_table_names():
        return
    if 'revoke_before_us' in {c['name'] for c in inspect(engine).get_columns('platform_account_restrictions')}:
        return
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('ALTER TABLE platform_account_restrictions ADD COLUMN revoke_before_us BIGINT NOT NULL DEFAULT 0')
    except OperationalError:
        if 'revoke_before_us' not in {c['name'] for c in inspect(engine).get_columns('platform_account_restrictions')}:
            raise


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
        "skus": {
            "image_url": "VARCHAR(500) DEFAULT ''",
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
            "hero_height": "INTEGER DEFAULT 640",
            "strip_tint": "BOOLEAN DEFAULT 1",
            "promises": "TEXT DEFAULT ''",
            "social_accounts": "TEXT DEFAULT '[]'",
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
        from app.services.assistant_identity import initialize_assistant_names
        initialize_assistant_names(db)
        # 平台运营＝平台管理员：启动时补齐全部质量能力，新环境无需再手工授权。
        from app.quality.service import provision_operators
        granted = provision_operators(db)
        if granted:
            logger.info("已为 %d 个平台运营账号补齐质量能力授权", granted)
    finally:
        db.close()
    _rebuild_c_projection()
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

@app.get("/login", include_in_schema=False)
@app.get("/login/", include_in_schema=False)
def merchant_login_page():
    return FileResponse(settings.web_dir / "b.html")


if settings.web_dir.exists():
    app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
