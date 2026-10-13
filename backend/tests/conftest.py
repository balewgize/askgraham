"""Shared pytest fixtures."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app() -> FastAPI:
    """A fresh app instance per test, so middleware/config state never leaks."""
    from main import create_app

    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the app. For endpoint tests that need no database."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def served_paths(app: FastAPI) -> set[str]:
    """Paths the app exposes, read from the OpenAPI schema.

    Introspecting `app.routes` is unreliable across Starlette versions —
    `include_router` may nest routes behind an object with no `.path`. The
    OpenAPI schema is the public contract, so asserting on it is both stable
    and more meaningful.
    """
    return set(app.openapi()["paths"])
