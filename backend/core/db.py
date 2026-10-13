"""Async SQLAlchemy engine and session management.

The engine is created lazily so importing this module never requires a reachable
database — that keeps unit tests, the CLI and Alembic free of live infrastructure.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Process-wide engine, created on first use."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_s,
            # Pre-ping guards against connections dropped by a restarted container.
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def dispose_engine() -> None:
    """Close all pooled connections. Called on application shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope for CLI commands and background jobs.

    Commits on clean exit, rolls back on error. Preferred over a FastAPI
    dependency anywhere outside a request.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session.

    Deliberately not decorated with `@asynccontextmanager`: FastAPI resolves
    async *generator* dependencies itself, and wrapping it would return an
    object FastAPI cannot yield from. The session is not committed here —
    read-only request handlers have nothing to write.
    """
    async with get_sessionmaker()() as session:
        yield session


__all__ = ["dispose_engine", "get_engine", "get_session", "get_sessionmaker", "session_scope"]
