import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["REDIS_URL"] = "memory"
os.environ["AGENT_MODE"] = "fallback"
os.environ["STRICT_DEPENDENCIES"] = "false"
os.environ["AGENT_REQUIRE_LLM"] = "false"
os.environ["RAG_REQUIRE_VECTORS"] = "false"
os.environ["EMBEDDING_PROVIDER"] = "ollama"
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
    get_redis().flush()
    with TestClient(app) as test_client:
        yield test_client
