from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/store.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    jwt_secret: str = "dev-secret-change-me-please-use-32b"
    jwt_expire_minutes: int = 60 * 24
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_reasoning: bool | None = None
    ollama_num_ctx: int = 4096
    ollama_num_predict: int = 256
    ollama_timeout_seconds: int = 45
    ollama_embed_model: str = "nomic-embed-text"
    chroma_path: str = "./data/chroma"
    agent_mode: str = "auto"
    session_max_chars: int = 2400
    agent_max_steps: int = 4
    agent_rate_limit_per_minute: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

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
