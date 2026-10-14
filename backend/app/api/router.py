from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.b_api import router as b_router
from app.api.c_api import router as c_router
from app.core.config import settings

router = APIRouter()
router.include_router(auth_router)
router.include_router(b_router)
router.include_router(c_router)


@router.get("/health")
def health():
    from app.db.redis_client import get_redis
    dialect = settings.database_url.split(":", 1)[0]
    return {"status": "ok", "database": dialect, "agent_mode": settings.agent_mode,
            "redis": "memory" if get_redis().using_memory else "redis"}
