"""Corpus ingest: `data/*.json` → Postgres.

Idempotent by construction. Every entity carries a content hash, so a re-run only
writes rows whose content actually changed. Re-scraping one essay and re-running
ingest must cost one row, not 233 — the same property the TypeScript pipeline
needed for its LLM caches, and the reason `content_hash` is on the schema.

Reading the corpus is pure and synchronous; only the writes are async.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.errors import ValidationError
from core.logging_config import log
from core.models import (
    Base,
    Essay,
    EssayFootnote,
    EssayParagraph,
    EssayPhase,
    GenerationMeta,
    IngestRun,
    PathStep,
    Phase,
    ReadingPath,
)

_MONTHS: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# "September 2024" -> (2024, 9). Anything else falls back to a bare year, then
# to None, which sorts last. Mirrors `dateKey()` in frontend/lib/essays.ts.
_FULL_DATE = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|october"
    r"|november|december)\s+(\d{4})$",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")


def date_key(date: str | None) -> tuple[int | None, int | None]:
    """Sortable (year, month). Undated essays return (None, None)."""
    if not date:
        return None, None
    full = _FULL_DATE.match(date.strip())
    if full:
        return int(full.group(2)), _MONTHS[full.group(1).lower()]
    year = _YEAR.search(date)
    return (int(year.group(1)), None) if year else (None, None)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def essay_content_hash(payload: dict[str, Any]) -> str:
    """Hash of the body only — ignores title/date so prose edits are isolated."""
    return _sha256(json.dumps(payload.get("paragraphs", []), ensure_ascii=False))


def essay_meta_hash(payload: dict[str, Any]) -> str:
    """Hash of everything except the body."""
    return _sha256(
        "|".join(
            str(payload.get(k, ""))
            for k in ("slug", "title", "url", "date", "word_count", "reading_time_min")
        )
    )


@dataclass
class IngestStats:
    essays_seen: int = 0
    essays_written: int = 0
    essays_skipped: int = 0
    paragraphs_written: int = 0
    footnotes_written: int = 0
    # Counted separately on purpose: these are different tables. Adding them
    # together produced a "phase tags: 608" report for a corpus that has 600
    # tags and 8 taxonomy phases.
    taxonomy_phases_written: int = 0
    phase_tags_written: int = 0
    paths_written: int = 0
    paths_skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "essays_seen": self.essays_seen,
            "essays_written": self.essays_written,
            "essays_skipped": self.essays_skipped,
            "paragraphs_written": self.paragraphs_written,
            "footnotes_written": self.footnotes_written,
            "taxonomy_phases_written": self.taxonomy_phases_written,
            "phase_tags_written": self.phase_tags_written,
            "paths_written": self.paths_written,
            "paths_skipped": self.paths_skipped,
        }


# ── corpus reading (sync, no database) ────────────────────────────────


def read_essay_files(data_dir: Path) -> list[dict[str, Any]]:
    essays_dir = data_dir / "essays"
    if not essays_dir.is_dir():
        raise ValidationError(f"no essays directory at {essays_dir}")

    out: list[dict[str, Any]] = []
    for path in sorted(essays_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{path.name} is not valid JSON: {exc}") from exc
        if not payload.get("slug"):
            raise ValidationError(f"{path.name} has no slug")
        out.append(payload)
    return out


def _read_optional(data_dir: Path, name: str) -> dict[str, Any] | None:
    path = data_dir / name
    if not path.is_file():
        return None
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


# ── writers (async) ───────────────────────────────────────────────────


async def _upsert_essays(
    session: AsyncSession, payloads: list[dict[str, Any]], stats: IngestStats
) -> None:
    existing = {
        slug: (content_hash, meta_hash)
        for slug, content_hash, meta_hash in (
            await session.execute(select(Essay.slug, Essay.content_hash, Essay.meta_hash))
        ).all()
    }

    changed: list[dict[str, Any]] = []
    for payload in payloads:
        stats.essays_seen += 1
        body = essay_content_hash(payload)
        meta = essay_meta_hash(payload)
        if existing.get(payload["slug"]) == (body, meta):
            stats.essays_skipped += 1
            continue
        changed.append(payload)

    if not changed:
        log.info("essays.unchanged", count=stats.essays_skipped)
        return

    slugs = [p["slug"] for p in changed]

    # Children are rewritten wholesale rather than diffed: they are derived data
    # and a body edit invalidates all of them anyway.
    await session.execute(delete(EssayParagraph).where(EssayParagraph.slug.in_(slugs)))
    await session.execute(delete(EssayFootnote).where(EssayFootnote.slug.in_(slugs)))
    await session.execute(delete(EssayPhase).where(EssayPhase.slug.in_(slugs)))

    for payload in changed:
        year, month = date_key(payload.get("date"))
        session.add(
            Essay(
                slug=payload["slug"],
                title=payload.get("title", ""),
                url=payload.get("url", ""),
                date=payload.get("date"),
                date_year=year,
                date_month=month,
                word_count=int(payload.get("word_count", 0)),
                reading_time_min=int(payload.get("reading_time_min", 0)),
                content_hash=essay_content_hash(payload),
                meta_hash=essay_meta_hash(payload),
                source="data/essays",
            )
        )
        stats.essays_written += 1
        stats.paragraphs_written += len(payload.get("paragraphs", []))
        stats.footnotes_written += len(payload.get("footnotes", []))

    await session.flush()
    # Bulk child inserts: 233 essays produce ~8.3k paragraph rows, and add_all()
    # would build 8.3k ORM objects for no benefit.
    await session.execute(
        insert(EssayParagraph),
        [
            {
                "slug": p["slug"],
                "position": i,
                "text": text,
            }
            for p in changed
            for i, text in enumerate(p.get("paragraphs", []))
        ],
    )
    await session.execute(
        insert(EssayFootnote),
        [
            {
                "slug": p["slug"],
                "marker": str(fn.get("id", i)),
                "position": i,
                "text": fn.get("text", ""),
            }
            for p in changed
            for i, fn in enumerate(p.get("footnotes", []))
        ],
    )


async def _upsert_taxonomy(session: AsyncSession, data_dir: Path, stats: IngestStats) -> None:
    taxonomy = _read_optional(data_dir, "taxonomy.json")
    if taxonomy is None:
        log.warning("taxonomy.missing", file="taxonomy.json")
        return

    known = set((await session.execute(select(Phase.id))).scalars().all())
    for phase in taxonomy.get("phases", []):
        if phase["id"] not in known:
            session.add(
                Phase(
                    id=phase["id"],
                    label=phase["label"],
                    order=int(phase.get("order", 0)),
                    description=phase.get("description", ""),
                )
            )
            stats.taxonomy_phases_written += 1

    await _set_generation_meta(
        session,
        artifact="taxonomy",
        version=int(taxonomy.get("version", 1)),
        source="taxonomy.json",
    )
    await session.flush()


async def _set_generation_meta(
    session: AsyncSession,
    *,
    artifact: str,
    model: str | None = None,
    version: int | None = None,
    generated: str | None = None,
    source: str | None = None,
) -> None:
    """Upsert one provenance row. Replaces rather than merges."""
    await session.execute(delete(GenerationMeta).where(GenerationMeta.artifact == artifact))
    session.add(
        GenerationMeta(
            artifact=artifact,
            model=model,
            version=version,
            generated=generated,
            source=source,
        )
    )


async def upsert_essay_phases(session: AsyncSession, data_dir: Path, stats: IngestStats) -> None:
    """`phases.json` is LLM output and optional — absent means 'not classified yet'.

    Replaced per slug rather than merged per (slug, phase). A merged insert only
    adds rows, so if an essay's tags change from [a, b] to [a] the stale (slug, b)
    row survives and the essay keeps a tag it no longer has. Comparing the whole
    list per essay is both simpler and correct.
    """
    phases_file = _read_optional(data_dir, "phases.json")
    if phases_file is None:
        log.warning("phases.missing", file="phases.json")
        return

    known_slugs = set((await session.execute(select(Essay.slug))).scalars().all())
    known_phases = set((await session.execute(select(Phase.id))).scalars().all())

    existing: dict[str, tuple[list[tuple[int, str]], str | None]] = {}
    for slug, phase_id, rank, content_hash in (
        await session.execute(
            select(EssayPhase.slug, EssayPhase.phase_id, EssayPhase.rank, EssayPhase.content_hash)
        )
    ).all():
        ranks, _hash = existing.setdefault(slug, ([], content_hash))
        ranks.append((rank, phase_id))
        ranks.sort()

    rows: list[dict[str, Any]] = []
    for slug, value in (phases_file.get("essays") or {}).items():
        if slug not in known_slugs:
            continue  # stale tag for an essay that no longer exists
        wanted = [p for p in value.get("phases", []) if p in known_phases]
        if not wanted:
            continue
        body_hash = value.get("hash") or _sha256(json.dumps(wanted))
        current, current_hash = existing.get(slug, ([], None))
        if [p for _r, p in current] == wanted and current_hash == body_hash:
            continue
        # Replace the whole set for this essay.
        await session.execute(delete(EssayPhase).where(EssayPhase.slug == slug))
        rows.extend(
            {
                "slug": slug,
                "phase_id": phase_id,
                "rank": rank,
                "why": value.get("why", ""),
                "content_hash": body_hash,
            }
            for rank, phase_id in enumerate(wanted)
        )

    if rows:
        await session.execute(insert(EssayPhase), rows)
        stats.phase_tags_written += len(rows)

    await _set_generation_meta(
        session,
        artifact="phases",
        model=phases_file.get("model"),
        version=phases_file.get("taxonomyVersion"),
        generated=phases_file.get("generated"),
        source="phases.json",
    )


async def upsert_paths(session: AsyncSession, data_dir: Path, stats: IngestStats) -> None:
    paths_file = _read_optional(data_dir, "paths.json")
    if paths_file is None:
        log.warning("paths.missing", file="paths.json")
        return

    existing = dict((await session.execute(select(ReadingPath.id, ReadingPath.hash))).all())
    wanted = {p["id"]: p.get("hash") for p in paths_file.get("paths", [])}

    # Rewrite a path when its hash changed OR it is not in the database at all —
    # iterating `wanted` rather than `existing` is what makes a first run write
    # anything, and what keeps a re-run a no-op.
    stale = [pid for pid, h in wanted.items() if existing.get(pid) != h]
    if stale:
        await session.execute(delete(PathStep).where(PathStep.path_id.in_(stale)))
        await session.execute(delete(ReadingPath).where(ReadingPath.id.in_(stale)))
        await session.flush()

    for path in sorted(paths_file.get("paths", []), key=lambda p: p.get("order", 0)):
        if path["id"] not in stale:
            stats.paths_skipped += 1
            continue
        session.add(
            ReadingPath(
                id=path["id"],
                title=path.get("title", ""),
                subtitle=path.get("subtitle", ""),
                description=path.get("description", ""),
                audience=path.get("audience", ""),
                order=int(path.get("order", 0)),
                hash=path.get("hash"),
            )
        )
        stats.paths_written += 1

    await session.flush()

    steps = [
        {
            "path_id": path["id"],
            "position": i,
            "slug": step["slug"],
            "note": step.get("note", ""),
        }
        for path in paths_file.get("paths", [])
        if path["id"] in stale
        for i, step in enumerate(path.get("steps", []))
    ]
    if steps:
        await session.execute(insert(PathStep), steps)

    await _set_generation_meta(
        session,
        artifact="paths",
        model=paths_file.get("model"),
        version=paths_file.get("version"),
        generated=paths_file.get("generated"),
        source="paths.json",
    )


# ── entry point ───────────────────────────────────────────────────────


async def ingest_corpus(session: AsyncSession, data_dir: Path | None = None) -> IngestStats:
    """Load the whole corpus into Postgres. Safe to run repeatedly."""
    source = data_dir or settings.data_dir
    stats = IngestStats()

    run = IngestRun(succeeded=False)
    session.add(run)
    await session.flush()

    try:
        payloads = read_essay_files(source)
        await _upsert_essays(session, payloads, stats)
        await _upsert_taxonomy(session, source, stats)
        await upsert_essay_phases(session, source, stats)
        await upsert_paths(session, source, stats)

        await session.flush()

        run.finished_at = datetime.now(UTC)
        run.essays_seen = stats.essays_seen
        run.essays_written = stats.essays_written
        run.essays_skipped = stats.essays_skipped
        run.succeeded = True
    except Exception:
        await session.rollback()
        log.exception("ingest.failed", data_dir=str(source))
        raise

    log.info("ingest.complete", **stats.as_dict())
    return stats


__all__ = [
    "Base",
    "IngestStats",
    "date_key",
    "essay_content_hash",
    "essay_meta_hash",
    "ingest_corpus",
    "read_essay_files",
    "upsert_essay_phases",
    "upsert_paths",
]
