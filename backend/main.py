"""FastAPI application factory.

Wires middleware, error handling, CORS and routers. Kept deliberately thin:
business logic lives in the service modules, not here.
"""

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from config import settings
from core import db
from core.errors import DomainError
from core.logging_config import configure_logging, log

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Open on startup, close on shutdown."""
    configure_logging()
    log.info(
        "startup",
        environment=settings.environment,
        data_dir=str(settings.data_dir),
    )
    try:
        yield
    finally:
        await db.dispose_engine()
        log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="RAG API for the Paul Graham essay corpus.",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    # ── middleware ────────────────────────────────────────────────────
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Bind a request id and emit one line per request with its latency."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                elapsed_ms=round(elapsed_ms, 2),
            )
            raise
        finally:
            structlog.contextvars.unbind_contextvars("request_id")

        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=round(elapsed_ms, 2),
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", REQUEST_ID_HEADER],
        )

    # ── error handling ────────────────────────────────────────────────
    @app.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    # ── routes ────────────────────────────────────────────────────────
    app.include_router(health_router)
    # Phase 3: app.include_router(api_router, prefix="/api/v1")

    return app


# ── health ────────────────────────────────────────────────────────

health_router = APIRouter(tags=["health"])


@health_router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness. Answers as long as the process is up. No dependencies touched."""
    return {"status": "ok"}


@health_router.get("/readyz")
async def readyz() -> JSONResponse:
    """Readiness. Verifies the database actually accepts queries.

    Container orchestrators gate traffic on this, so it must exercise the real
    dependency rather than just returning 200.
    """
    try:
        async with db.get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("readiness_failed", error=str(exc))
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "down", "detail": str(exc)[:200]},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "ok", "database": "up", "environment": settings.environment},
    )


app = create_app()
