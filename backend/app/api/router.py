from fastapi import APIRouter
from fastapi.responses import JSONResponse

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


@router.get("/ready")
def readiness():
    from sqlalchemy import text
    from app.db.session import engine
    from app.db.redis_client import get_redis
    checks = {"database": False, "redis": False}
    try:
        with engine.connect() as connection:
            checks["database"] = connection.scalar(text("SELECT 1")) == 1
        if settings.strict_dependencies and engine.dialect.name != "mysql":
            checks["database"] = False
    except Exception:
        pass
    try:
        checks["redis"] = get_redis().verify()
    except Exception:
        pass
    ready = all(checks.values())
    return JSONResponse(status_code=200 if ready else 503, content={
        "status": "ready" if ready else "unavailable", "checks": checks,
        "database": engine.dialect.name, "redis": "memory" if get_redis().using_memory else "redis",
        "strict_dependencies": settings.strict_dependencies, "require_llm": settings.agent_require_llm,
        "acceptance_environment": settings.acceptance_environment,
        "require_vectors": settings.rag_require_vectors,
        "model_provider": settings.model_provider,
        "model": settings.cloud_model if settings.model_provider == "cloud" else settings.ollama_model,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model_name,
        "embedding_dimensions": settings.cloud_embedding_dimensions if settings.embedding_provider == "zhipu" else None,
    })
