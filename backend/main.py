"""FastAPI application factory.

Wires middleware, error handling, CORS and routers. Kept deliberately thin:
business logic lives in the service modules, not here.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")

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


# ── search ────────────────────────────────────────────────────────

search_router = APIRouter(tags=["search"])

SearchMode = Literal["hybrid", "vector", "lexical"]

# Enough prose to make a result scannable without shipping whole chunks to the
# palette. Cut at a word boundary so it never ends mid-word.
_SNIPPET_CHARS = 280


def _snippet(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _SNIPPET_CHARS:
        return collapsed
    cut = collapsed[:_SNIPPET_CHARS].rsplit(" ", 1)[0]
    return f"{cut}…"


class SearchHitModel(BaseModel):
    slug: str
    title: str
    date: str | None
    reading_time_min: int
    score: float
    start_paragraph: int
    end_paragraph: int
    snippet: str
    vector_rank: int | None = None
    lexical_rank: int | None = None
    title_rank: int | None = None
    rerank_score: float | None = None


class SearchTimings(BaseModel):
    vector_ms: float
    lexical_ms: float
    title_ms: float
    rerank_ms: float
    elapsed_ms: float


class SearchResponse(BaseModel):
    query: str
    mode: str
    count: int
    results: list[SearchHitModel]
    timings: SearchTimings


@search_router.get("/search", response_model=SearchResponse)
async def search(
    session: AsyncSession = Depends(db.get_session),
    q: str = Query(min_length=1, max_length=500, description="Search query."),
    limit: int = Query(
        default=settings.search_default_limit,
        ge=1,
        le=settings.search_max_limit,
    ),
    mode: SearchMode = Query(
        default="hybrid",
        description="Which first-stage arms to run. Used by Phase 8 ablations.",
    ),
    dedupe: bool = Query(
        default=True,
        description="Collapse to the best chunk per essay (the palette lists essays).",
    ),
    rerank: bool | None = Query(
        default=None,
        description="Override cross-encoder reranking. Defaults to RERANK_ENABLED.",
    ),
) -> SearchResponse:
    """Hybrid search over the chunk index.

    Imports `rag.retrieval` lazily so the embedder's ONNX stack is only touched
    by a search, not by app import or a health check.
    """
    from rag.retrieval import dedupe_by_essay, hybrid_search

    # When collapsing to one hit per essay, fetch extra candidates so the head
    # can still fill `limit` after several chunks of the same essay collapse.
    fetch_limit = min(settings.search_max_limit, limit * 3) if dedupe else limit
    outcome = await hybrid_search(session, q, limit=fetch_limit, mode=mode, rerank=rerank)
    hits = dedupe_by_essay(outcome.hits)[:limit] if dedupe else outcome.hits

    return SearchResponse(
        query=q,
        mode=mode,
        count=len(hits),
        results=[
            SearchHitModel(
                slug=hit.slug,
                title=hit.title,
                date=hit.date,
                reading_time_min=hit.reading_time_min,
                score=hit.score,
                start_paragraph=hit.start_paragraph,
                end_paragraph=hit.end_paragraph,
                snippet=_snippet(hit.text),
                vector_rank=hit.vector_rank,
                lexical_rank=hit.lexical_rank,
                title_rank=hit.title_rank,
                rerank_score=hit.rerank_score,
            )
            for hit in hits
        ],
        timings=SearchTimings(
            vector_ms=round(outcome.vector_ms, 2),
            lexical_ms=round(outcome.lexical_ms, 2),
            title_ms=round(outcome.title_ms, 2),
            rerank_ms=round(outcome.rerank_ms, 2),
            elapsed_ms=round(outcome.elapsed_ms, 2),
        ),
    )


# ── chat ──────────────────────────────────────────────────────────

chat_router = APIRouter(tags=["chat"])


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Bounded so a long conversation cannot grow the request (or the bill)
    # without limit. The client trims; the server enforces.
    history: list[ChatTurn] = Field(default_factory=list, max_length=settings.chat_max_history)


def _sse(payload: dict[str, Any]) -> str:
    """One server-sent event. Every event is a JSON object with a `type`."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@chat_router.post("/chat")
async def chat(
    request: ChatRequest,
    session: AsyncSession = Depends(db.get_session),
) -> StreamingResponse:
    """Retrieve for the question, then stream a cited answer.

    Retrieval finishes before the response starts, so the request's database
    session is no longer needed once the stream is open — only the model call
    is streamed. Events: `sources`, then `delta` per token, then `done`, or an
    `error` event if generation fails partway.
    """
    from llm.generation import Source, Turn, stream_answer
    from rag.retrieval import hybrid_search

    outcome = await hybrid_search(session, request.message, limit=settings.chat_context_chunks)
    sources = [
        Source(
            slug=hit.slug,
            title=hit.title,
            start_paragraph=hit.start_paragraph,
            end_paragraph=hit.end_paragraph,
            text=hit.text,
        )
        for hit in outcome.hits
    ]
    history = [Turn(role=turn.role, content=turn.content) for turn in request.history]

    async def event_stream() -> AsyncIterator[str]:
        yield _sse(
            {
                "type": "sources",
                "sources": [
                    {
                        "slug": s.slug,
                        "title": s.title,
                        "start_paragraph": s.start_paragraph,
                        "end_paragraph": s.end_paragraph,
                    }
                    for s in sources
                ],
            }
        )
        usage: dict[str, int] = {}
        started = time.perf_counter()
        try:
            async for delta in stream_answer(
                question=request.message, history=history, sources=sources, usage=usage
            ):
                yield _sse({"type": "delta", "text": delta})
        except Exception as exc:
            log.exception("chat.failed", question_chars=len(request.message))
            yield _sse({"type": "error", "message": f"generation failed: {exc}"[:200]})
            return

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        log.info("chat.complete", elapsed_ms=elapsed_ms, chunks=len(sources), **usage)
        yield _sse({"type": "done", "elapsed_ms": elapsed_ms, "usage": usage})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        # `no-transform` asks any intermediary (including Next's dev proxy) not
        # to compress the body. Gzipping an event stream breaks browser stream
        # readers, and `no-cache` keeps it from being buffered.
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Content-Encoding": "identity",
            "X-Accel-Buffering": "no",
        },
    )


app = create_app()
