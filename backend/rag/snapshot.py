"""Snapshot export: Postgres → `frontend/snapshot/`.

The frontend reads this directory at build time instead of `data/`. That keeps
`next build` hermetic — no database, no network — so a Vercel preview built from
a fork works, and the backend only needs to be awake for actual chat traffic.

Layout mirrors `data/` exactly, so the frontend switch is a single path change:

    frontend/snapshot/
    ├── index.json       sorted newest-first, undated last
    ├── essays/<slug>.json
    ├── taxonomy.json
    ├── phases.json
    └── paths.json

Written to a sibling temp directory and swapped into place, so an interrupted
export can never leave the frontend reading half a corpus.

Provenance (`model`, `generated`, `version`) comes from the `generation_meta`
table, which `ingest` fills from the source JSON. It exists so the files this
writes say which model produced them, rather than reporting null.
"""

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import BACKEND_DIR
from core.logging_config import log
from core.models import (
    Essay,
    EssayFootnote,
    EssayParagraph,
    EssayPhase,
    GenerationMeta,
    PathStep,
    Phase,
    ReadingPath,
)

SNAPSHOT_DIR = BACKEND_DIR.parent / "frontend" / "snapshot"

# Canonical display order, matching sortIndex() in frontend/lib/essays.ts.
# Verified to reproduce that ordering exactly across all 233 essays.
#
# `nulls_last()` is load-bearing: Postgres defaults DESC to NULLS FIRST, which
# would put the two undated essays at the *top* of the catalog instead of the
# bottom. date_month is null for year-only dates like "1993", where TS uses 0,
# so those also sort last within their year.
_ORDER_BY = (
    Essay.date_year.desc().nulls_last(),
    Essay.date_month.desc().nulls_last(),
    Essay.title,
)


@dataclass
class SnapshotStats:
    essays: int = 0
    paragraphs: int = 0
    footnotes: int = 0
    phases: int = 0
    paths: int = 0
    path_steps: int = 0
    words: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "essays": self.essays,
            "paragraphs": self.paragraphs,
            "footnotes": self.footnotes,
            "phase_tags": self.phases,
            "paths": self.paths,
            "path_steps": self.path_steps,
            "words": self.words,
        }


def _write_json(path: Path, payload: Any) -> None:
    """Write UTF-8 JSON matching the formatting of the source corpus."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def _load_essays(session: AsyncSession) -> list[dict[str, Any]]:
    """Every essay with its paragraphs and footnotes, in canonical order.

    Children are fetched in two bulk queries rather than per essay: 233 essays
    would otherwise be 466 extra round trips.
    """
    essays = (await session.execute(select(Essay).order_by(*_ORDER_BY))).scalars().all()

    paragraphs: dict[str, list[str]] = {}
    for slug, text in (
        await session.execute(
            select(EssayParagraph.slug, EssayParagraph.text).order_by(
                EssayParagraph.slug, EssayParagraph.position
            )
        )
    ).all():
        paragraphs.setdefault(slug, []).append(text)

    # `marker` is the original `[n]` id. The corpus stores it as a string and
    # the frontend's Footnote type expects a string, so it is emitted verbatim.
    footnotes: dict[str, list[dict[str, str]]] = {}
    for slug, marker, text in (
        await session.execute(
            select(EssayFootnote.slug, EssayFootnote.marker, EssayFootnote.text).order_by(
                EssayFootnote.slug, EssayFootnote.position
            )
        )
    ).all():
        footnotes.setdefault(slug, []).append({"id": marker, "text": text})

    out: list[dict[str, Any]] = []
    for essay in essays:
        out.append(
            {
                "slug": essay.slug,
                "title": essay.title,
                "url": essay.url,
                "date": essay.date,
                "word_count": essay.word_count,
                "reading_time_min": essay.reading_time_min,
                "paragraphs": paragraphs.get(essay.slug, []),
                "footnotes": footnotes.get(essay.slug, []),
            }
        )
    return out


async def _load_index(session: AsyncSession, essays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The light catalog the index page and prev/next navigation use."""
    return [
        {
            "slug": e["slug"],
            "title": e["title"],
            "date": e["date"],
            "word_count": e["word_count"],
            "reading_time_min": e["reading_time_min"],
        }
        for e in essays
    ]


async def _load_generation_meta(session: AsyncSession) -> dict[str, GenerationMeta]:
    rows = (await session.execute(select(GenerationMeta))).scalars().all()
    return {row.artifact: row for row in rows}


async def _load_taxonomy(
    session: AsyncSession, meta_by_artifact: dict[str, GenerationMeta]
) -> dict[str, Any]:
    phases = (await session.execute(select(Phase).order_by(Phase.order))).scalars().all()
    taxonomy_meta = meta_by_artifact.get("taxonomy")
    return {
        "version": taxonomy_meta.version if taxonomy_meta and taxonomy_meta.version else 1,
        "phases": [
            {
                "id": p.id,
                "label": p.label,
                "order": p.order,
                "description": p.description,
            }
            for p in phases
        ],
    }


async def _load_phases(
    session: AsyncSession, meta_by_artifact: dict[str, GenerationMeta]
) -> dict[str, Any]:
    """Rebuild the per-essay phase map from the rank-ordered rows.

    `rank` is preserved because the reader's filter chips key off rank 0 — the
    model returns phases most-relevant-first and flattening that would change
    which chip counts an essay.
    """
    rows = (
        await session.execute(
            select(
                EssayPhase.slug,
                EssayPhase.phase_id,
                EssayPhase.rank,
                EssayPhase.why,
                EssayPhase.content_hash,
            ).order_by(EssayPhase.slug, EssayPhase.rank)
        )
    ).all()

    essays: dict[str, dict[str, Any]] = {}
    for slug, phase_id, _rank, why, content_hash in rows:
        entry = essays.setdefault(slug, {"phases": [], "why": why, "hash": content_hash})
        entry["phases"].append(phase_id)

    taxonomy_meta = meta_by_artifact.get("taxonomy")
    phases_meta = meta_by_artifact.get("phases")
    return {
        "taxonomyVersion": taxonomy_meta.version if taxonomy_meta and taxonomy_meta.version else 1,
        "model": phases_meta.model if phases_meta else None,
        "generated": phases_meta.generated if phases_meta else None,
        "essays": essays,
    }


async def _load_paths(
    session: AsyncSession, meta_by_artifact: dict[str, GenerationMeta]
) -> dict[str, Any]:
    paths = (await session.execute(select(ReadingPath).order_by(ReadingPath.order))).scalars().all()

    steps: dict[str, list[dict[str, str]]] = {}
    for path_id, slug, note in (
        await session.execute(
            select(PathStep.path_id, PathStep.slug, PathStep.note).order_by(
                PathStep.path_id, PathStep.position
            )
        )
    ).all():
        steps.setdefault(path_id, []).append({"slug": slug, "note": note})

    paths_meta = meta_by_artifact.get("paths")
    return {
        "version": paths_meta.version if paths_meta and paths_meta.version else 1,
        "model": paths_meta.model if paths_meta else None,
        "generated": paths_meta.generated if paths_meta else None,
        "paths": [
            {
                "id": p.id,
                "title": p.title,
                "subtitle": p.subtitle,
                "description": p.description,
                "audience": p.audience,
                "order": p.order,
                "steps": steps.get(p.id, []),
                "hash": p.hash,
            }
            for p in paths
        ],
    }


async def export_snapshot(session: AsyncSession, out_dir: Path | None = None) -> SnapshotStats:
    """Write the frontend's build-time corpus. Safe to re-run."""
    target = out_dir or SNAPSHOT_DIR
    staging = target.with_name(f"{target.name}.tmp")
    stats = SnapshotStats()
    generated = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        meta_by_artifact = await _load_generation_meta(session)
        essays = await _load_essays(session)
        index = await _load_index(session, essays)
        taxonomy = await _load_taxonomy(session, meta_by_artifact)
        phases = await _load_phases(session, meta_by_artifact)
        paths = await _load_paths(session, meta_by_artifact)

        for essay in essays:
            _write_json(staging / "essays" / f"{essay['slug']}.json", essay)
        stats.essays = len(essays)
        stats.words = sum(e["word_count"] for e in essays)
        stats.paragraphs = sum(len(e["paragraphs"]) for e in essays)
        stats.footnotes = sum(len(e["footnotes"]) for e in essays)

        _write_json(staging / "index.json", index)
        _write_json(staging / "taxonomy.json", taxonomy)
        _write_json(staging / "phases.json", phases)
        _write_json(staging / "paths.json", paths)
        stats.phases = len(phases["essays"])
        stats.paths = len(paths["paths"])
        stats.path_steps = sum(len(p["steps"]) for p in paths["paths"])

        # A manifest so the build can tell whether its snapshot is stale
        # without diffing 233 files.
        _write_json(
            staging / "manifest.json",
            {
                "generated": generated,
                "essays": stats.essays,
                "words": stats.words,
                "model": paths["model"],
            },
        )

        # Swap into place. Removing then renaming leaves a brief window with no
        # snapshot at all, which is preferable to serving a partial one.
        if target.exists():
            shutil.rmtree(target)
        staging.rename(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        log.exception("snapshot.failed", target=str(target))
        raise

    log.info("snapshot.complete", path=str(target), **stats.as_dict())
    return stats


__all__ = ["SNAPSHOT_DIR", "SnapshotStats", "export_snapshot"]
