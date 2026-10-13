"""Find essays related to a given essay.

Relatedness is cosine similarity between the source essay's **centroid** — the
mean of its chunk embeddings — and every other essay's chunks.

Why the centroid and not something cheaper or simpler:

- **Not one chunk.** Using the opening chunk would relate the essay to whatever
  its first paragraph is about, which is often the hook, not the subject.
- **Not the full text at request time.** Re-embedding the essay would load the
  ONNX model into a read path that otherwise only touches Postgres. The chunk
  vectors are already there, so the whole feature is one aggregate query.

Results are deduped to the best chunk per essay: a reader wants essays, not
passages. This is the same collapse the search endpoint does for the palette.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.errors import NotFoundError
from core.models import Chunk, Essay


def centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    """Element-wise mean of a set of vectors.

    Pure, so the arithmetic is tested without a database. Raising on ragged input
    rather than padding is deliberate: a dimension mismatch means the index holds
    vectors from two different models, which is a bug worth surfacing, not
    smoothing over.
    """
    if not vectors:
        raise ValueError("cannot average no vectors")
    dim = len(vectors[0])
    sums = [0.0] * dim
    for vector in vectors:
        if len(vector) != dim:
            raise ValueError("vectors have mismatched dimensions")
        for index, value in enumerate(vector):
            sums[index] += value
    count = len(vectors)
    return [value / count for value in sums]


@dataclass(frozen=True)
class RelatedEssay:
    """One related essay, and the best-matching passage within it."""

    slug: str
    title: str
    date: str | None
    reading_time_min: int
    similarity: float
    start_paragraph: int
    end_paragraph: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "date": self.date,
            "reading_time_min": self.reading_time_min,
            "similarity": round(self.similarity, 4),
            "start_paragraph": self.start_paragraph,
            "end_paragraph": self.end_paragraph,
        }


async def _essay_vectors(session: AsyncSession, slug: str) -> list[list[float]]:
    rows = await session.execute(
        select(Chunk.embedding).where(Chunk.slug == slug, Chunk.embedding.is_not(None))
    )
    return [list(vector) for (vector,) in rows.all() if vector is not None]


async def find_related_essays(
    session: AsyncSession,
    slug: str,
    *,
    limit: int | None = None,
) -> list[RelatedEssay]:
    """Essays most similar to `slug`, best first.

    Raises `NotFoundError` for an unknown slug. Returns an empty list when the
    essay exists but has not been indexed yet, matching search's behaviour: a
    missing index is an empty answer, not an error.
    """
    if await session.get(Essay, slug) is None:
        raise NotFoundError(f"no essay with slug {slug!r}")

    vectors = await _essay_vectors(session, slug)
    if not vectors:
        return []

    top_k = limit if limit is not None else settings.related_default_limit
    source = centroid(vectors)
    distance = Chunk.embedding.cosine_distance(source)
    # Overfetch, because several of the nearest chunks will belong to the same
    # essay and collapse to one.
    fetch = min(settings.search_max_limit, max(top_k * 5, top_k))

    rows = await session.execute(
        select(
            Chunk.slug,
            Chunk.start_paragraph,
            Chunk.end_paragraph,
            Essay.title,
            Essay.date,
            Essay.reading_time_min,
            distance.label("distance"),
        )
        .join(Essay, Essay.slug == Chunk.slug)
        .where(Chunk.slug != slug, Chunk.embedding.is_not(None))
        .order_by(distance)
        .limit(fetch)
    )

    seen: set[str] = set()
    out: list[RelatedEssay] = []
    for row in rows.all():
        if row.slug in seen:
            continue
        seen.add(row.slug)
        out.append(
            RelatedEssay(
                slug=row.slug,
                title=row.title,
                date=row.date,
                reading_time_min=row.reading_time_min,
                # Cosine distance is in [0, 2]; similarity in [-1, 1].
                similarity=max(-1.0, min(1.0, 1.0 - float(row.distance))),
                start_paragraph=row.start_paragraph,
                end_paragraph=row.end_paragraph,
            )
        )
        if len(out) >= top_k:
            break
    return out


__all__ = ["RelatedEssay", "centroid", "find_related_essays"]
