import os

if not os.environ.get("QA_NATIVE_DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite://"
    os.environ["REDIS_URL"] = "memory"
os.environ["AGENT_MODE"] = "fallback"
if not os.environ.get("QA_NATIVE_DATABASE_URL"):
    os.environ["STRICT_DEPENDENCIES"] = "false"
os.environ["AGENT_REQUIRE_LLM"] = "false"
os.environ["RAG_REQUIRE_VECTORS"] = "false"
os.environ["EMBEDDING_PROVIDER"] = "ollama"
os.environ["CLOUD_EMBEDDING_BASE_URL"] = ""
os.environ["CLOUD_EMBEDDING_API_KEY"] = ""
os.environ["CLOUD_EMBEDDING_API_KEY_FILE"] = ""
os.environ["CLOUD_EMBEDDING_FALLBACK_MODELS"] = ""
os.environ["QA_NATIVE_ENABLED"] = "false"
os.environ["QA_NATIVE_MYSQL_PASSWORD"] = ""
os.environ["JWT_SECRET"] = "test-secret"
os.environ["CHROMA_PATH"] = "./data/test-chroma"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    import app.models.tables  # noqa: F401
    from app.db.base import Base
    from app.db.redis_client import get_redis
    from app.db.session import engine
    from app.main import app

    Base.metadata.drop_all(bind=engine)
    if os.environ.get("QA_NATIVE_DATABASE_URL"):
        get_redis().delete_pattern("*")
    else:
        get_redis().flush()
    with TestClient(app) as test_client:
        yield test_client
