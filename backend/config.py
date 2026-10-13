"""Application settings, loaded from the environment.

All configuration lives here so nothing else reads the environment directly.
Values come from real env vars, with a `.env` file for local development.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# `backend/` — the repo root is one level up. Kept as a module constant so
# CLI commands and Alembic resolve `data/` the same way the app does.
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── app ────────────────────────────────────────────────────────────
    app_name: str = "askgraham-api"
    environment: Literal["local", "dev", "prod"] = "local"
    debug: bool = False
    log_level: str = "INFO"
    # Comma-separated. Empty means same-origin only (frontend proxies the API).
    cors_origins: str = ""

    # ── database ───────────────────────────────────────────────────────
    # Default matches the docker-compose service. Override in production.
    database_url: str = "postgresql+asyncpg://askgraham:askgraham@localhost:5433/askgraham"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_s: int = 30

    # ── llm ────────────────────────────────────────────────────────────
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Default matches frontend/scripts/*.ts so a ported run reproduces the same
    # cache keys. Changing this invalidates cached LLM output by design: the
    # path cache hash includes the model name.
    openrouter_model: str = "openai/gpt-oss-120b"
    # LLM calls are slow; the TypeScript had no timeout, which means a hung
    # request hangs the run forever.
    openrouter_timeout_s: float = 120.0
    llm_max_attempts: int = 3
    classify_concurrency: int = 4

    @property
    def llm_configured(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def data_dir(self) -> Path:
        """Repo-root `data/` — the 233 essays plus derived metadata."""
        return REPO_ROOT / "data"

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"


@lru_cache
def get_settings() -> Settings:
    """Cached settings. Safe because configuration never changes at runtime."""
    return Settings()


settings = get_settings()

__all__ = ["BACKEND_DIR", "REPO_ROOT", "Settings", "get_settings", "settings"]
