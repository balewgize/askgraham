"""Tag every essay with the startup stage it helps most.

    uv run python cli.py classify              # only essays whose text changed
    uv run python cli.py classify --limit 5
    uv run python cli.py classify --force      # ignore the cache
    uv run python cli.py classify --dry-run

Reads:  data/taxonomy.json, data/essays/*.json, data/phases.json (cache)
Writes: data/phases.json

Ported from frontend/scripts/classify-essays.ts. The prompt, the response schema
and the cache key are reproduced exactly, because the cache key is derived from
essay text: any drift there would re-classify all 233 essays and re-bill for them.
`tests/test_classify.py` asserts the stored hashes still match.

Cost is small by design. The cache keys on essay content, so a re-run only pays
for essays that are new or edited. Change the prompt or taxonomy and pass
`--force`.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.errors import ValidationError
from core.logging_config import log
from core.models import Essay, EssayPhase, Phase
from llm.client import LLMError, OpenRouterClient, collapse_whitespace, map_bounded
from rag.ingest import date_key, read_essay_files

PHASES_FILENAME = "phases.json"
TAXONOMY_FILENAME = "taxonomy.json"


def essay_cache_hash(essay: dict[str, Any]) -> str:
    """Cache key for one essay: sha256 of its paragraphs joined by newlines.

    Deliberately NOT the same as `rag.ingest.essay_content_hash`, which hashes a
    JSON encoding for change detection. This one reproduces the TypeScript
    exactly, and the committed `data/phases.json` holds these values.
    """
    joined = "\n".join(essay.get("paragraphs", []))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def build_prompt(essay: dict[str, Any], taxonomy: dict[str, Any]) -> tuple[str, str]:
    """System/user prompts. Wording is load-bearing — it was tuned against output."""
    phases = "\n".join(
        f"- {p['id']}: {p['label']} — {p['description']}" for p in taxonomy["phases"]
    )
    # Built by concatenation rather than one long literal so the source stays
    # inside the line limit. The concatenated result is byte-identical to the
    # TypeScript template literal, which matters: the wording is tuned.
    system = (
        "You label Paul Graham essays by the startup stage they help most.\n"
        "\n"
        "Phases (choose one or more; put the single most relevant first):\n"
        f"{phases}\n"
        "\n"
        "Rules:\n"
        "- Use only the phase ids listed above.\n"
        "- Include every stage the essay genuinely helps, not just one.\n"
        '- Use "any" only for essays that are not stage-specific (craft, work, thinking).\n'
        '- "why": one concrete sentence, max 20 words, telling a founder what they get '
        'from it. No filler like "This essay..."'
    )
    date = essay.get("date") or "unknown"
    body = "\n\n".join(essay.get("paragraphs", []))
    user = f"Title: {essay['title']}\nDate: {date}\n\n{body}"
    return system, user


def response_schema(taxonomy: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "phases": {
                "type": "array",
                "items": {"type": "string", "enum": [p["id"] for p in taxonomy["phases"]]},
                "minItems": 1,
            },
            "why": {"type": "string"},
        },
        "required": ["phases", "why"],
        "additionalProperties": False,
    }


def validate_result(parsed: Any, taxonomy: dict[str, Any]) -> dict[str, Any]:
    """Keep only known phase ids, deduped, and require a usable `why`."""
    valid = {p["id"] for p in taxonomy["phases"]}
    raw_phases = parsed.get("phases") if isinstance(parsed, dict) else None
    phases: list[str] = []
    if isinstance(raw_phases, list):
        for value in raw_phases:
            if isinstance(value, str) and value in valid and value not in phases:
                phases.append(value)
    if not phases:
        raise LLMError("no valid phases returned")

    raw_why = parsed.get("why") if isinstance(parsed, dict) else None
    why = collapse_whitespace(raw_why) if isinstance(raw_why, str) else ""
    if not why:
        raise LLMError("empty why returned")

    return {"phases": phases, "why": why}


# ── the run ───────────────────────────────────────────────────────────


@dataclass
class ClassifyStats:
    total: int = 0
    cached: int = 0
    attempted: int = 0
    classified: int = 0
    failures: list[str] = field(default_factory=list)
    model: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "cached": self.cached,
            "attempted": self.attempted,
            "classified": self.classified,
            "failed": len(self.failures),
            "model": self.model,
        }


def load_existing(path: Path) -> dict[str, dict[str, Any]]:
    """Previous results, or empty on a first run. A malformed cache is not fatal."""
    try:
        cached: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))["essays"]
    except OSError, json.JSONDecodeError, KeyError, TypeError:
        return {}
    return cached


def write_phases(path: Path, payload: dict[str, Any]) -> None:
    """Write with the same shape and key order as the TypeScript."""
    ordered = {
        "taxonomyVersion": payload["taxonomyVersion"],
        "model": payload["model"],
        "generated": payload["generated"],
        "essays": payload["essays"],
    }
    path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def classify_essays(
    data_dir: Path,
    *,
    limit: int | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> ClassifyStats:
    """Tag essays and write `data/phases.json`. Idempotent via the content hash."""
    out_path = data_dir / PHASES_FILENAME

    try:
        taxonomy = json.loads((data_dir / TAXONOMY_FILENAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read {TAXONOMY_FILENAME}: {exc}") from exc

    essays = read_essay_files(data_dir)
    # Display order (newest first, undated last) so --limit is deterministic.
    essays.sort(
        key=lambda e: (
            -(date_key(e.get("date"))[0] or 0),
            -(date_key(e.get("date"))[1] or 0),
            e.get("title", ""),
        )
    )

    existing = load_existing(out_path)
    todo = [
        e for e in essays if force or existing.get(e["slug"], {}).get("hash") != essay_cache_hash(e)
    ]
    stats = ClassifyStats(
        total=len(essays), cached=len(essays) - len(todo), model=settings.openrouter_model
    )

    if limit and limit > 0:
        todo = todo[:limit]
    stats.attempted = len(todo)

    log.info("classify.plan", **stats.as_dict())
    if dry_run:
        for essay in todo:
            log.info("classify.would", slug=essay["slug"])
        return stats
    if not todo:
        log.info("classify.nothing_to_do")
        return stats

    client = OpenRouterClient()
    if not client.configured:
        raise ValidationError("OPENROUTER_API_KEY is not set")

    schema = response_schema(taxonomy)

    async with httpx.AsyncClient(follow_redirects=True) as http:

        async def one(essay: dict[str, Any]) -> dict[str, Any]:
            system, user = build_prompt(essay, taxonomy)
            parsed = await client.chat_json(
                system=system,
                user=user,
                schema=schema,
                schema_name="essay_phases",
                app_title="Ask Graham classifier",
                client=http,
            )
            return validate_result(parsed, taxonomy)

        results = await map_bounded(todo, one, concurrency=max(1, settings.classify_concurrency))

    merged = dict(existing)
    current = {e["slug"] for e in essays}
    for essay, result, error in results:
        if error is not None:
            stats.failures.append(f"{essay['slug']}: {error}")
            log.warning("classify.failed", slug=essay["slug"], error=str(error)[:200])
            continue
        merged[essay["slug"]] = {**result, "hash": essay_cache_hash(essay)}
        stats.classified += 1
        log.info("classify.ok", slug=essay["slug"], phases=", ".join(result["phases"]))

    # Drop tags for essays that no longer exist, so the file cannot drift.
    essays_out = {slug: value for slug, value in merged.items() if slug in current}

    if not dry_run:
        write_phases(
            out_path,
            {
                "taxonomyVersion": taxonomy.get("version", 1),
                "model": settings.openrouter_model,
                "generated": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "essays": essays_out,
            },
        )

    return stats


# ── database path ─────────────────────────────────────────────────────
# The snapshot reads `essay_phases` from Postgres, so classification has to land
# there too. `ingest` also reads data/phases.json directly; this exists so a
# classify run can be followed immediately by a snapshot without a full ingest.


async def sync_phases_to_db(session: AsyncSession, data_dir: Path) -> int:
    """Replace `essay_phases` with the contents of data/phases.json."""
    payload = json.loads((data_dir / PHASES_FILENAME).read_text(encoding="utf-8"))
    tags = payload.get("essays") or {}

    known_essays = set((await session.execute(select(Essay.slug))).scalars().all())
    known_phases = set((await session.execute(select(Phase.id))).scalars().all())

    await session.execute(delete(EssayPhase))
    rows: list[dict[str, Any]] = []
    skipped = 0
    for slug, value in tags.items():
        if slug not in known_essays:
            continue
        for rank, phase_id in enumerate(value.get("phases", [])):
            if phase_id not in known_phases:
                skipped += 1
                continue
            rows.append(
                {
                    "slug": slug,
                    "phase_id": phase_id,
                    "rank": rank,
                    "why": value.get("why", ""),
                    "content_hash": value.get("hash"),
                }
            )
    if rows:
        await session.execute(insert(EssayPhase), rows)
    if skipped:
        log.warning("classify.unknown_phases", count=skipped)
    return len(rows)


__all__ = [
    "ClassifyStats",
    "build_prompt",
    "classify_essays",
    "essay_cache_hash",
    "load_existing",
    "response_schema",
    "sync_phases_to_db",
    "validate_result",
    "write_phases",
]
