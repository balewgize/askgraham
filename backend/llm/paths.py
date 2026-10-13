"""Curate ordered reading paths through the catalogue.

    uv run python cli.py paths                    # only paths whose spec changed
    uv run python cli.py paths --only=start-here
    uv run python cli.py paths --force            # regenerate everything
    uv run python cli.py paths --dry-run

Reads:  data/paths.spec.json, data/index.json, data/phases.json, data/paths.json (cache)
Writes: data/paths.json

Ported from frontend/scripts/generate-paths.ts. The cache key is
`sha256(JSON.stringify(spec) + MODEL)[:16]`, reproduced exactly so the committed
`data/paths.json` stays valid. `tests/test_paths.py` asserts both stored hashes
still match; a drift there would regenerate every path and re-bill for it.

Generation is sequential, matching the TypeScript. `paths.spec.json` has two
entries, so concurrency would buy nothing and only make failures harder to read.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from config import settings
from core.errors import ValidationError
from core.logging_config import log
from llm.client import (
    InvalidResponseError,
    OpenRouterClient,
    collapse_whitespace,
)

SPEC_FILENAME = "paths.spec.json"
PATHS_FILENAME = "paths.json"
INDEX_FILENAME = "index.json"
PHASES_FILENAME = "phases.json"


def spec_cache_hash(spec: dict[str, Any], model: str) -> str:
    """Cache key for one path spec: sha256 of its JSON plus the model name.

    Includes the model because a different model is a different result. Uses
    compact separators to match `JSON.stringify`, and `ensure_ascii=False`
    because `JSON.stringify` emits non-ASCII literally.
    """
    encoded = json.dumps(spec, separators=(",", ":"), ensure_ascii=False) + model
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def build_catalog(index: list[dict[str, Any]], phases: dict[str, Any]) -> str:
    """One line per essay: slug | title (date, minutes) [tags] why.

    Read in file order, NOT sorted. The TypeScript reads index.json as stored,
    and the prompt's ordering is part of what the model sees.
    """
    lines = []
    for entry in index:
        tagged = phases.get(entry["slug"], {})
        tags = ",".join(tagged.get("phases", [])) or "untagged"
        why = tagged.get("why", "")
        date = entry.get("date") or "undated"
        lines.append(
            f"- {entry['slug']} | {entry['title']} "
            f"({date}, {entry['reading_time_min']} min) [{tags}] {why}"
        )
    return "\n".join(lines)


def build_prompt(
    spec: dict[str, Any], index: list[dict[str, Any]], phases: dict[str, Any]
) -> tuple[str, str]:
    """System/user prompts. Wording is load-bearing — it was tuned against output."""
    system = (
        "You curate reading paths through Paul Graham's essay catalog for new readers.\n"
        "\n"
        "You are given the full catalog. Each line is: "
        "slug | title (date, reading time) [stage tags] one-line summary.\n"
        "\n"
        "Pick essays and order them into a path. Rules:\n"
        "- Use only slugs that appear in the catalog. Never invent one.\n"
        "- Return exactly one entry per essay. No duplicates.\n"
        "- First essay: short, self-contained, zero prior knowledge required.\n"
        "- Order so ideas build progressively; put foundational or widely cited essays "
        "before essays that assume them.\n"
        "- Skip dated, news-pegged, or purely historical pieces unless they define a "
        "lasting idea.\n"
        "- No two essays should make the same point.\n"
        '- "note": one concrete sentence, max 22 words, telling the reader why this '
        "essay is here and why now. No filler.\n"
        '- "description": 2 sentences describing the path\'s arc, max 45 words.'
    )
    user = (
        f"Path: {spec['title']} — {spec['subtitle']}\n"
        f"Audience: {spec['audience']}\n"
        f"Goal: {spec['intent']}\n"
        f"Choose between {spec['minSteps']} and {spec['maxSteps']} essays.\n"
        "\n"
        f"Catalog:\n{build_catalog(index, phases)}"
    )
    return system, user


def response_schema(spec: dict[str, Any], slugs: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "steps": {
                "type": "array",
                "minItems": spec["minSteps"],
                "maxItems": spec["maxSteps"],
                "items": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "enum": slugs},
                        "note": {"type": "string"},
                    },
                    "required": ["slug", "note"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["description", "steps"],
        "additionalProperties": False,
    }


def validate_result(parsed: Any, valid_slugs: set[str]) -> dict[str, Any]:
    """Accept only real slugs, drop duplicates, and require a description.

    The rejection names the invented slugs so a repair retry can fix them.
    """
    if not isinstance(parsed, dict):
        raise InvalidResponseError("response was not a JSON object")

    raw_description = parsed.get("description")
    description = collapse_whitespace(raw_description) if isinstance(raw_description, str) else ""
    if not description:
        raise InvalidResponseError("empty `description`")

    raw_steps = parsed.get("steps")
    if not isinstance(raw_steps, list):
        raise InvalidResponseError("`steps` was missing or not a list")

    steps: list[dict[str, str]] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in raw_steps:
        if not isinstance(raw, dict):
            continue
        slug = raw.get("slug")
        if not isinstance(slug, str):
            continue
        if slug not in valid_slugs:
            if slug not in rejected:
                rejected.append(slug)
            continue
        if slug in seen:
            continue  # duplicates are dropped silently: harmless, not a mistake
        seen.add(slug)
        raw_note = raw.get("note")
        steps.append(
            {
                "slug": slug,
                "note": collapse_whitespace(raw_note) if isinstance(raw_note, str) else "",
            }
        )

    if rejected:
        raise InvalidResponseError(
            f"slugs not in the catalog: {rejected[:8]}. Use only slugs from the catalog."
        )
    if not steps:
        raise InvalidResponseError("no steps returned")

    return {"description": description, "steps": steps}


@dataclass
class PathsStats:
    total: int = 0
    selected: int = 0
    cached: int = 0
    generated: int = 0
    failures: list[str] = field(default_factory=list)
    model: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "selected": self.selected,
            "cached": self.cached,
            "generated": self.generated,
            "failed": len(self.failures),
            "model": self.model,
        }


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read {label}: {exc}") from exc


def write_paths(path: Path, payload: dict[str, Any]) -> None:
    """Write with the same shape and key order as the TypeScript."""
    ordered = {
        "version": payload["version"],
        "model": payload["model"],
        "generated": payload["generated"],
        "paths": payload["paths"],
    }
    path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def generate_paths(
    data_dir: Path,
    *,
    only: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> PathsStats:
    """Curate reading paths and write `data/paths.json`. Cached per spec."""
    out_path = data_dir / PATHS_FILENAME
    spec_file = _read_json(data_dir / SPEC_FILENAME, SPEC_FILENAME)
    index = _read_json(data_dir / INDEX_FILENAME, INDEX_FILENAME)
    phases_file = _read_json(data_dir / PHASES_FILENAME, PHASES_FILENAME)
    phase_map: dict[str, Any] = phases_file.get("essays", {})

    existing = _read_json(out_path, PATHS_FILENAME) if out_path.exists() else {}
    by_id = {p["id"]: p for p in existing.get("paths", [])}

    specs = spec_file["paths"]
    selected = [p for p in specs if not only or p["id"] == only]
    pending = [
        p
        for p in selected
        if force
        or by_id.get(p["id"], {}).get("hash") != spec_cache_hash(p, settings.openrouter_model)
    ]

    stats = PathsStats(
        total=len(specs),
        selected=len(selected),
        cached=len(selected) - len(pending),
        model=settings.openrouter_model,
    )
    log.info("paths.plan", **stats.as_dict())

    if dry_run:
        for spec in pending:
            log.info(
                "paths.would",
                path_id=spec["id"],
                min_steps=spec["minSteps"],
                max_steps=spec["maxSteps"],
            )
        return stats
    if not pending:
        log.info("paths.nothing_to_do")
        return stats

    client = OpenRouterClient()
    if not client.configured:
        raise ValidationError("OPENROUTER_API_KEY is not set")

    slugs = [e["slug"] for e in index]
    results = dict(by_id)

    async with httpx.AsyncClient(follow_redirects=True) as http:
        for spec in pending:
            system, user = build_prompt(spec, index, phase_map)
            try:
                parsed = await client.chat_json(
                    system=system,
                    user=user,
                    schema=response_schema(spec, slugs),
                    schema_name="reading_path",
                    app_title="Ask Graham path curator",
                    client=http,
                )
                draft = validate_result(parsed, set(slugs))
            except Exception as exc:
                stats.failures.append(f"{spec['id']}: {exc}")
                log.warning("paths.failed", path_id=spec["id"], error=str(exc)[:200])
                continue

            results[spec["id"]] = {
                "id": spec["id"],
                "title": spec["title"],
                "subtitle": spec["subtitle"],
                "description": draft["description"],
                "audience": spec["audience"],
                "order": specs.index(spec) + 1,
                "steps": draft["steps"],
                "hash": spec_cache_hash(spec, settings.openrouter_model),
            }
            stats.generated += 1
            minutes = sum(
                next((e["reading_time_min"] for e in index if e["slug"] == s["slug"]), 0)
                for s in draft["steps"]
            )
            log.info(
                "paths.ok",
                path_id=spec["id"],
                steps=len(draft["steps"]),
                minutes=minutes,
            )

    # Preserve spec order and renumber, so `order` always reflects the file.
    paths = [results[p["id"]] for p in specs if p["id"] in results]
    paths = [{**p, "order": i + 1} for i, p in enumerate(paths)]

    write_paths(
        out_path,
        {
            "version": spec_file.get("version", 1),
            "model": settings.openrouter_model,
            "generated": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "paths": paths,
        },
    )
    return stats


__all__ = [
    "PathsStats",
    "build_catalog",
    "build_prompt",
    "generate_paths",
    "response_schema",
    "spec_cache_hash",
    "validate_result",
    "write_paths",
]
