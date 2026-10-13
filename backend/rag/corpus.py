"""Read a single essay for API consumers.

`snapshot.py` reads the whole corpus to write build-time files. This is the
runtime counterpart: one essay, on demand, for the chat's citation panel. Kept
separate so the snapshot's bulk path is not dragged into a request.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import NotFoundError
from core.models import Essay, EssayFootnote, EssayParagraph


async def load_essay(session: AsyncSession, slug: str) -> dict[str, Any]:
    """One essay with its paragraphs and footnotes, or `NotFoundError`."""
    essay = await session.get(Essay, slug)
    if essay is None:
        raise NotFoundError(f"no essay with slug {slug!r}")

    paragraphs = (
        (
            await session.execute(
                select(EssayParagraph.text)
                .where(EssayParagraph.slug == slug)
                .order_by(EssayParagraph.position)
            )
        )
        .scalars()
        .all()
    )

    footnotes = (
        await session.execute(
            select(EssayFootnote.marker, EssayFootnote.text)
            .where(EssayFootnote.slug == slug)
            .order_by(EssayFootnote.position)
        )
    ).all()

    return {
        "slug": essay.slug,
        "title": essay.title,
        "url": essay.url,
        "date": essay.date,
        "word_count": essay.word_count,
        "reading_time_min": essay.reading_time_min,
        "paragraphs": list(paragraphs),
        "footnotes": [{"id": marker, "text": text} for marker, text in footnotes],
    }


__all__ = ["load_essay"]
