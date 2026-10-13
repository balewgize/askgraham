"""Health endpoints.

`/healthz` must never touch the database — that is the whole point of splitting
liveness from readiness. `/readyz` must genuinely exercise Postgres, so these
tests assert the failure path too, not just the happy one.
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from .conftest import served_paths


def _break_sessionmaker() -> None:
    """Stand-in for core.db.get_sessionmaker that fails the way a dead DB would.

    Synchronous on purpose: the real one is a plain function returning a
    sessionmaker, so an `async def` here would raise TypeError instead and let
    the readiness test pass for the wrong reason.
    """
    raise RuntimeError("connection refused")


async def test_healthz_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_healthz_does_not_touch_database(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Liveness must answer even when the database is unreachable."""
    monkeypatch.setattr("core.db.get_sessionmaker", _break_sessionmaker)

    response = await client.get("/healthz")
    assert response.status_code == 200


async def test_readyz_reports_503_when_db_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.db.get_sessionmaker", _break_sessionmaker)

    response = await client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["database"] == "down"
    assert "connection refused" in body["detail"]


async def test_request_id_header_is_echoed(client: AsyncClient) -> None:
    """Every response carries a request id so logs and responses correlate."""
    response = await client.get("/healthz")
    assert response.headers.get("X-Request-ID")


async def test_request_id_is_preserved_when_supplied(client: AsyncClient) -> None:
    """An upstream id is passed through rather than replaced."""
    response = await client.get("/healthz", headers={"X-Request-ID": "trace-me-123"})
    assert response.headers["X-Request-ID"] == "trace-me-123"


def test_health_endpoints_are_in_the_api_contract(app: FastAPI) -> None:
    paths = served_paths(app)
    assert "/healthz" in paths
    assert "/readyz" in paths
