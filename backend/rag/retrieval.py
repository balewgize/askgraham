"""Hybrid retrieval: chunk and embed the corpus, then search it two ways and fuse.

Search runs two cheap first-stage retrievals whose failures are uncorrelated:

- **dense** — pgvector cosine distance over the HNSW index. Finds paraphrases
  and synonym matches that share no words with the query.
- **lexical** — Postgres `ts_rank_cd` over a generated tsvector. Finds exact
  terms, names and rare words that a small dense model blurs.

The two are combined with **Reciprocal Rank Fusion**, which needs only the
*ranks*, not the two scores' incomparable scales. A cross-encoder then reorders
the fused head — it is too expensive to run over the whole corpus, which is the
whole reason for the two-stage design.

`index_chunks` is the other half: chunk each essay, embed only the chunks whose
text actually changed, and store them. It is idempotent through `content_hash`,
and it invalidates everything when the embedding model or chunking parameters
change, because a vector produced by a different model is not comparable.
"""

import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.logging_config import log
from core.models import Chunk, Essay, EssayParagraph, GenerationMeta
from rag.chunking import Chunk as ChunkSpec
from rag.chunking import chunk_paragraphs
from rag.embeddings import (
    Embedder,
    Reranker,
    embed_documents_async,
    embed_query_async,
    get_embedder,
    rerank_async,
)

RetrievalMode = Literal["hybrid", "vector", "lexical"]

CHUNKS_ARTIFACT = "chunks"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def chunk_signature(embedder: Embedder) -> str:
    """What produced the index. A change here means every embedding is stale.

    Stored in `generation_meta.source` so the check survives a process restart;
    comparing against in-memory state alone would re-embed on every boot.
    """
    return (
        f"model={embedder.model_name};dim={settings.embedding_dim};"
        f"max_tokens={settings.chunk_max_tokens};overlap={settings.chunk_overlap_tokens}"
    )


# ── indexing ──────────────────────────────────────────────────────────


@dataclass
class IndexStats:
    essays_seen: int = 0
    essays_indexed: int = 0
    essays_skipped: int = 0
    chunks_written: int = 0
    chunks_skipped: int = 0
    tokens: int = 0
    elapsed_s: float = 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "essays_seen": self.essays_seen,
            "essays_indexed": self.essays_indexed,
            "essays_skipped": self.essays_skipped,
            "chunks_written": self.chunks_written,
            "chunks_skipped": self.chunks_skipped,
            "tokens": self.tokens,
            "elapsed_s": round(self.elapsed_s, 2),
        }


async def _paragraphs_by_slug(session: AsyncSession) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    rows = await session.execute(
        select(EssayParagraph.slug, EssayParagraph.text).order_by(
            EssayParagraph.slug, EssayParagraph.position
        )
    )
    for slug, text in rows.all():
        out.setdefault(slug, []).append(text)
    return out


async def _existing_hashes(session: AsyncSession) -> dict[str, dict[int, str]]:
    out: dict[str, dict[int, str]] = {}
    rows = await session.execute(select(Chunk.slug, Chunk.position, Chunk.content_hash))
    for slug, position, content_hash in rows.all():
        out.setdefault(slug, {})[position] = content_hash
    return out


async def index_chunks(
    session: AsyncSession,
    *,
    force: bool = False,
    limit: int | None = None,
    embedder: Embedder | None = None,
) -> IndexStats:
    """Chunk and embed the corpus. Re-embeds only what changed.

    Returns counts rather than raising on a partial run: one essay that fails to
    embed must not cost the other 232, and the caller reports the shortfall.
    """
    started = time.perf_counter()
    model = embedder or get_embedder()
    stats = IndexStats()

    signature = chunk_signature(model)
    meta = await session.get(GenerationMeta, CHUNKS_ARTIFACT)
    # Any of: an explicit --force, no index yet, or a different model/params.
    stale_all = force or meta is None or meta.model != model.model_name or meta.source != signature

    essays = (await session.execute(select(Essay.slug).order_by(Essay.slug))).scalars().all()
    # `--limit` is a genuine subset of the run, not just a write filter: it is
    # for spot checks, so it must also skip chunking the essays it excludes.
    if limit is not None:
        essays = essays[:limit]
    paragraphs = await _paragraphs_by_slug(session)
    existing = {} if stale_all else await _existing_hashes(session)

    # (slug, chunk-spec) pairs awaiting an embedding.
    pending: list[tuple[str, ChunkSpec]] = []
    stale_slugs: list[str] = []
    for slug in essays:
        stats.essays_seen += 1
        chunks = chunk_paragraphs(
            slug,
            paragraphs.get(slug, []),
            count_tokens=model.count_tokens,
        )
        wanted = {c.position: _sha256(c.text) for c in chunks}
        if not stale_all and existing.get(slug, {}) == wanted:
            stats.essays_skipped += 1
            stats.chunks_skipped += len(chunks)
            continue
        stale_slugs.append(slug)
        pending.extend((slug, chunk) for chunk in chunks)

    stats.essays_indexed = len(stale_slugs)

    if not pending:
        stats.elapsed_s = time.perf_counter() - started
        log.info("index.nothing_to_do", **stats.as_dict())
        return stats

    await session.execute(delete(Chunk).where(Chunk.slug.in_(stale_slugs)))
    await session.flush()

    texts = [chunk.text for _slug, chunk in pending]
    stats.tokens = sum(chunk.token_count for _slug, chunk in pending)
    embeddings: list[list[float]] = []
    batch = max(1, settings.embedding_batch_size)
    for start in range(0, len(texts), batch):
        embeddings.extend(await embed_documents_async(texts[start : start + batch], embedder=model))

    rows = [
        {
            "slug": slug,
            "position": chunk.position,
            "start_paragraph": chunk.start_paragraph,
            "end_paragraph": chunk.end_paragraph,
            "text": chunk.text,
            "token_count": chunk.token_count,
            "content_hash": _sha256(chunk.text),
            "embedding": vector,
        }
        for (slug, chunk), vector in zip(pending, embeddings, strict=True)
    ]
    await session.execute(insert(Chunk), rows)
    stats.chunks_written = len(rows)

    # Replace the provenance row so a later run can tell what built this index.
    await session.execute(delete(GenerationMeta).where(GenerationMeta.artifact == CHUNKS_ARTIFACT))
    session.add(
        GenerationMeta(
            artifact=CHUNKS_ARTIFACT,
            model=model.model_name,
            version=1,
            generated=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source=signature,
        )
    )

    stats.elapsed_s = time.perf_counter() - started
    log.info("index.complete", **stats.as_dict())
    return stats


# ── fusion ────────────────────────────────────────────────────────────


def rrf_fuse(
    *rankings: dict[int, int],
    k: int = 60,
) -> dict[int, float]:
    """Reciprocal Rank Fusion of any number of `{id: 1-based rank}` maps.

    `score(d) = Σ 1 / (k + rank_i(d))`. Ranks rather than scores because cosine
    distance and `ts_rank_cd` are not on a common scale and cannot be added
    without a normalization nobody can defend. A document missing from a ranking
    simply contributes nothing.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for doc_id, rank in ranking.items():
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


@dataclass
class SearchHit:
    slug: str
    title: str
    date: str | None
    reading_time_min: int
    text: str
    score: float
    start_paragraph: int
    end_paragraph: int
    vector_rank: int | None = None
    lexical_rank: int | None = None
    rerank_score: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "date": self.date,
            "reading_time_min": self.reading_time_min,
            "text": self.text,
            "score": round(self.score, 6),
            "start_paragraph": self.start_paragraph,
            "end_paragraph": self.end_paragraph,
            "vector_rank": self.vector_rank,
            "lexical_rank": self.lexical_rank,
            "rerank_score": None if self.rerank_score is None else round(self.rerank_score, 6),
        }


@dataclass
class SearchResult:
    hits: list[SearchHit] = field(default_factory=list)
    vector_ms: float = 0.0
    lexical_ms: float = 0.0
    rerank_ms: float = 0.0
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "hits": len(self.hits),
            "vector_ms": round(self.vector_ms, 2),
            "lexical_ms": round(self.lexical_ms, 2),
            "rerank_ms": round(self.rerank_ms, 2),
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


async def _vector_ranks(
    session: AsyncSession, query_vector: list[float], limit: int
) -> dict[int, int]:
    distance = Chunk.embedding.cosine_distance(query_vector)
    rows = await session.execute(
        select(Chunk.id).where(Chunk.embedding.is_not(None)).order_by(distance).limit(limit)
    )
    return {chunk_id: rank for rank, (chunk_id,) in enumerate(rows.all(), start=1)}


async def _lexical_ranks(session: AsyncSession, query: str, limit: int) -> dict[int, int]:
    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(Chunk.tsv, tsquery)
    rows = await session.execute(
        select(Chunk.id).where(Chunk.tsv.op("@@")(tsquery)).order_by(rank.desc()).limit(limit)
    )
    return {chunk_id: rank for rank, (chunk_id,) in enumerate(rows.all(), start=1)}


async def hybrid_search(
    session: AsyncSession,
    query: str,
    *,
    limit: int | None = None,
    mode: RetrievalMode = "hybrid",
    rerank: bool | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> SearchResult:
    """Search chunks and return the head, optionally cross-encoder reranked."""
    text = query.strip()
    if not text:
        return SearchResult()

    started = time.perf_counter()
    top_k = limit if limit is not None else settings.search_default_limit
    candidates = max(top_k, settings.search_candidates)
    use_rerank = settings.rerank_enabled if rerank is None else rerank
    result = SearchResult()

    vector_ranks: dict[int, int] = {}
    lexical_ranks: dict[int, int] = {}

    if mode in ("hybrid", "vector"):
        step = time.perf_counter()
        query_vector = await embed_query_async(text, embedder=embedder)
        vector_ranks = await _vector_ranks(session, query_vector, candidates)
        result.vector_ms = (time.perf_counter() - step) * 1000

    if mode in ("hybrid", "lexical"):
        step = time.perf_counter()
        lexical_ranks = await _lexical_ranks(session, text, candidates)
        result.lexical_ms = (time.perf_counter() - step) * 1000

    fused = rrf_fuse(vector_ranks, lexical_ranks, k=settings.rrf_k)
    if not fused:
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        log.info("search.complete", mode=mode, query_chars=len(text), **result.as_dict())
        return result

    head = sorted(fused, key=lambda cid: (-fused[cid], cid))
    # Reranking is the expensive stage, so the head it sees is capped by
    # `rerank_candidates`, independent of how many results the caller asked for.
    head_size = settings.rerank_candidates if use_rerank else top_k
    head = head[: max(1, head_size)]

    rows = await session.execute(
        select(
            Chunk.id,
            Chunk.slug,
            Chunk.start_paragraph,
            Chunk.end_paragraph,
            Chunk.text,
            Essay.title,
            Essay.date,
            Essay.reading_time_min,
        )
        .join(Essay, Essay.slug == Chunk.slug)
        .where(Chunk.id.in_(head))
    )
    fetched = {row.id: row for row in rows.all()}
    ordered = [fetched[cid] for cid in head if cid in fetched]

    rerank_scores: list[float] | None = None
    if use_rerank and len(ordered) > 1:
        step = time.perf_counter()
        rerank_scores = await rerank_async(text, [row.text for row in ordered], reranker=reranker)
        result.rerank_ms = (time.perf_counter() - step) * 1000

    indexed = list(enumerate(ordered))
    if rerank_scores is not None:
        indexed.sort(key=lambda pair: (-rerank_scores[pair[0]], fused[pair[1].id]))
    else:
        indexed.sort(key=lambda pair: (-fused[pair[1].id], pair[1].id))

    for original_index, row in indexed[:top_k]:
        result.hits.append(
            SearchHit(
                slug=row.slug,
                title=row.title,
                date=row.date,
                reading_time_min=row.reading_time_min,
                text=row.text,
                score=(
                    rerank_scores[original_index] if rerank_scores is not None else fused[row.id]
                ),
                start_paragraph=row.start_paragraph,
                end_paragraph=row.end_paragraph,
                vector_rank=vector_ranks.get(row.id),
                lexical_rank=lexical_ranks.get(row.id),
                rerank_score=rerank_scores[original_index] if rerank_scores is not None else None,
            )
        )

    result.elapsed_ms = (time.perf_counter() - started) * 1000
    log.info("search.complete", mode=mode, query_chars=len(text), **result.as_dict())
    return result


def dedupe_by_essay(hits: list[SearchHit]) -> list[SearchHit]:
    """Collapse chunk hits to the best chunk per essay, preserving order.

    The command palette lists essays, not passages. The first hit per slug is
    already the best-ranked one, so this is a stable filter rather than a
    re-sort.
    """
    seen: set[str] = set()
    out: list[SearchHit] = []
    for hit in hits:
        if hit.slug in seen:
            continue
        seen.add(hit.slug)
        out.append(hit)
    return out


__all__ = [
    "IndexStats",
    "RetrievalMode",
    "SearchHit",
    "SearchResult",
    "chunk_signature",
    "dedupe_by_essay",
    "hybrid_search",
    "index_chunks",
    "rrf_fuse",
]
