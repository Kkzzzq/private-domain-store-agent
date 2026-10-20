from pathlib import Path
from typing import Literal
from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/store.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    jwt_secret: str = "dev-secret-change-me-please-use-32b"
    jwt_expire_minutes: int = 60 * 24
    auth_login_limit: int = Field(default=60, ge=1)
    auth_register_limit: int = Field(default=20, ge=1)
    demo_login_enabled: bool = True
    demo_login_username: str = 'merchant'
    demo_login_password: str = 'merchant123'
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_reasoning: bool | None = None
    ollama_num_ctx: int = 4096
    ollama_num_predict: int = 256
    ollama_timeout_seconds: int = 45
    ollama_embed_model: str = "nomic-embed-text"
    embedding_provider: Literal["ollama", "zhipu"] = "ollama"
    cloud_embedding_model: str = "embedding-3"
    cloud_embedding_dimensions: int = Field(default=1024, ge=256, le=2048)
    cloud_timeout_seconds: int = Field(default=45, ge=1, le=180)
    chroma_path: str = "./data/chroma"
    agent_mode: str = "auto"
    model_provider: str = "ollama"
    cloud_api_key: str = ""
    cloud_api_key_file: str = ""
    cloud_api_style: Literal["qwen", "zhipu"] = "qwen"
    cloud_base_url: str = ""
    cloud_model: str = "qwen-plus-2025-04-28"
    cloud_max_tokens: int = 800
    cloud_fallback_models: str = ""
    cloud_fallback_cooldown_seconds: int = Field(default=300, ge=1, le=3600)
    session_max_chars: int = 2400
    agent_max_steps: int = 4
    recommendation_max_steps: int = Field(default=6, ge=3, le=8)
    agent_rate_limit_per_minute: int = 30
    strict_dependencies: bool = False
    agent_require_llm: bool = False
    rag_require_vectors: bool = False
    chroma_collection: str = "store_knowledge"
    acceptance_environment: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def embedding_model_name(self) -> str:
        return self.cloud_embedding_model if self.embedding_provider == "zhipu" else self.ollama_embed_model

    @property
    def backend_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def knowledge_dir(self) -> Path:
        return self.backend_root / "knowledge"

    @property
    def web_dir(self) -> Path:
        sibling = self.backend_root.parent / "web"
        if sibling.exists():
            return sibling
        return self.backend_root / "web"


settings = Settings()
