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

    # ── retrieval ──────────────────────────────────────────────────────
    # Chunking. `max_tokens` is deliberately below the model's 512-token
    # truncation limit so no chunk is silently cut off before embedding.
    chunk_max_tokens: int = 384
    chunk_overlap_tokens: int = 64
    # Embeddings are local ONNX: free, offline, reproducible. The model name is
    # the only knob; swapping it changes the vector width and needs a migration.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    # Empty means fastembed's default cache (HF_HOME, or ~/.cache/fastembed).
    embedding_cache_dir: str = ""
    embedding_batch_size: int = 64
    # Cross-encoder reranker. Off means RRF order is final; the Phase 8 ablation
    # flips this to price the quality it buys.
    rerank_enabled: bool = True
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    # Upper bound on how many fused candidates the cross-encoder scores. This is
    # the dominant cost of a search (the two first-stage arms are ~30ms combined),
    # so it is capped independently of how many results the caller asks for.
    rerank_candidates: int = 20
    # RRF constant. 60 is the value from the original paper and the usual
    # default; Phase 8 sweeps it.
    rrf_k: int = 60
    # Field boost for a title match, relative to the dense and body-lexical
    # arms. A title is short and intentional, so matching it is stronger
    # evidence than matching one body chunk — the BM25F idea, in RRF form.
    title_boost: float = 3.0
    # Candidates fetched from each arm (vector, lexical) before fusion.
    search_candidates: int = 50
    search_default_limit: int = 10
    search_max_limit: int = 50

    # ── chat ───────────────────────────────────────────────────────────
    # Passages put in front of the model. More context helps until it starts
    # burying the useful chunk; eight is a paragraph budget, not a token one.
    chat_context_chunks: int = 8
    # Prior turns echoed to the model for follow-ups. Capped so a long
    # conversation cannot grow the request without bound.
    chat_max_history: int = 12

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
    def export_dir(self) -> Path:
        """`frontend/public/export/` — downloadable bundles, served statically."""
        return REPO_ROOT / "frontend" / "public" / "export"

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"


@lru_cache
def get_settings() -> Settings:
    """Cached settings. Safe because configuration never changes at runtime."""
    return Settings()


settings = get_settings()

__all__ = ["BACKEND_DIR", "REPO_ROOT", "Settings", "get_settings", "settings"]
