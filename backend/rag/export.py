"""Downloadable corpus bundles: Postgres → `frontend/public/export/`.

Ported from the deleted `frontend/scripts/export-corpus.ts`, which was the last
TypeScript file the site needed. Keeping it in Python means `data/` has one
writer and the reader and the downloads are built from the same rows, so they
cannot disagree about what the corpus contains.

Output mirrors the old script exactly, because the `/export` page's links and
labels depend on it:

    essays.md               all essays in one LLM-friendly document
    essays.jsonl            one full essay JSON per line
    md/<slug>.md            one markdown file per essay, with front-matter
    notebooklm/<decade>.md  decade bundles, each under NotebookLM's 500k-word cap
    paths/<id>.md           a reading path: intro plus its essays in order
    askgraham-export.zip    essays.md + essays.jsonl + every markdown file
    manifest.json           counts and sizes for the download page

Written to a sibling temp directory and swapped into place, so an interrupted
run can never leave the download page pointing at half a corpus.
"""

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.logging_config import log
from rag.snapshot import load_essays, load_generation_meta, load_paths

SOURCE = "https://www.paulgraham.com/articles.html"
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def fmt_int(n: int) -> str:
    """Thousands-separated, matching `Number.toLocaleString("en-US")`."""
    return f"{n:,}"


def word_count(text: str) -> int:
    """Whitespace-delimited words. `str.split()` already drops empty runs."""
    return len(text.split())


def fmt_date(date: str | None) -> str:
    return date or "undated"


def decade_of(date: str | None) -> str:
    match = _YEAR_RE.search(date) if date else None
    if not match:
        return "undated"
    return f"{int(match.group(1)) // 10 * 10}s"


def meta_line(essay: dict[str, Any]) -> str:
    return (
        f"_{fmt_date(essay['date'])} · {fmt_int(essay['word_count'])} words · "
        f"{essay['reading_time_min']} min read · [original]({essay['url']})_"
    )


def essay_markdown(essay: dict[str, Any], level: int) -> str:
    """One essay as markdown, starting at `level` (`#` standalone, `##` in a bundle)."""
    heading = "#" * level
    parts = [f"{heading} {essay['title']}", meta_line(essay)]
    parts.extend(p.strip() for p in essay["paragraphs"])
    if essay["footnotes"]:
        parts.append(f"{'#' * (level + 1)} Notes")
        parts.append(
            "\n".join(f"- **[{f['id']}]** {f['text'].strip()}" for f in essay["footnotes"])
        )
    return "\n\n".join(parts)


def front_matter(essay: dict[str, Any]) -> str:
    def quoted(value: Any) -> str:
        return '"' + str(value).replace('"', '\\"') + '"'

    date = quoted(essay["date"]) if essay["date"] else "null"
    return "\n".join(
        [
            "---",
            f"title: {quoted(essay['title'])}",
            f"slug: {essay['slug']}",
            f"date: {date}",
            f"url: {quoted(essay['url'])}",
            f"word_count: {essay['word_count']}",
            f"reading_time_min: {essay['reading_time_min']}",
            "---",
        ]
    )


def collection(title: str, subtitle: str, essays: list[dict[str, Any]]) -> str:
    header = [f"# {title}", f"_{subtitle}_"]
    body = [essay_markdown(essay, 2) for essay in essays]
    return "\n\n".join([*header, "---", *body]) + "\n"


def _iso_now() -> str:
    """UTC ISO-8601 with milliseconds, matching `Date.toISOString()`."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class ExportStats:
    essays: int = 0
    words: int = 0
    bundles: int = 0
    paths: int = 0
    files: int = 0
    bytes: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "essays": self.essays,
            "words": self.words,
            "bundles": self.bundles,
            "paths": self.paths,
            "files": self.files,
            "bytes": self.bytes,
        }


async def export_corpus(session: AsyncSession, out_dir: Path | None = None) -> ExportStats:
    """Write the downloadable corpus bundles. Safe to re-run."""
    target = out_dir or settings.export_dir
    staging = target.with_name(f"{target.name}.tmp")
    stats = ExportStats()
    generated = _iso_now()

    essays = await load_essays(session)
    meta_by_artifact = await load_generation_meta(session)
    paths = (await load_paths(session, meta_by_artifact))["paths"]
    by_slug = {essay["slug"]: essay for essay in essays}
    total_words = sum(essay["word_count"] for essay in essays)

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    # `(path, bytes)` pairs that also become zip members. The zip is written
    # last, from this list, so it can never include a partially-written file.
    entries: list[tuple[str, bytes]] = []
    manifest_files: list[dict[str, Any]] = []

    def write(rel_path: str, content: str) -> bytes:
        data = content.encode("utf-8")
        path = staging / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        entries.append((rel_path, data))
        return data

    try:
        merged = collection(
            "Paul Graham's Essays",
            f"{fmt_int(len(essays))} essays · {fmt_int(total_words)} words · [source]({SOURCE})",
            essays,
        )
        data = write("essays.md", merged)
        manifest_files.append(
            {
                "path": "essays.md",
                "bytes": len(data),
                "words": word_count(merged),
                "kind": "all",
                "label": f"All {fmt_int(len(essays))} essays (single file)",
            }
        )

        jsonl = (
            "\n".join(
                json.dumps(essay, ensure_ascii=False, separators=(",", ":")) for essay in essays
            )
            + "\n"
        )
        data = write("essays.jsonl", jsonl)
        manifest_files.append(
            {
                "path": "essays.jsonl",
                "bytes": len(data),
                "words": 0,
                "kind": "jsonl",
                "label": "essays.jsonl — one essay per line",
            }
        )

        for essay in essays:
            write(
                f"md/{essay['slug']}.md", f"{front_matter(essay)}\n\n{essay_markdown(essay, 1)}\n"
            )

        by_decade: dict[str, list[dict[str, Any]]] = {}
        for essay in essays:
            by_decade.setdefault(decade_of(essay["date"]), []).append(essay)
        decades = sorted(
            by_decade,
            key=lambda d: (d == "undated", -(int(d[:4]) if d != "undated" else 0)),
        )
        for decade in decades:
            group = by_decade[decade]
            words = sum(essay["word_count"] for essay in group)
            content = collection(
                f"Paul Graham's Essays — {decade}",
                f"{fmt_int(len(group))} essays · {fmt_int(words)} words · [source]({SOURCE})",
                group,
            )
            data = write(f"notebooklm/{decade}.md", content)
            manifest_files.append(
                {
                    "path": f"notebooklm/{decade}.md",
                    "bytes": len(data),
                    "words": word_count(content),
                    "kind": "bundle",
                    "label": f"{decade} essays",
                }
            )

        for path in paths:
            steps = [s for s in path["steps"] if s["slug"] in by_slug]
            group = [by_slug[s["slug"]] for s in steps]
            order = "\n".join(
                f"{i + 1}. **{by_slug[s['slug']]['title']}** — {s['note']}"
                for i, s in enumerate(steps)
            )
            intro = [
                f"# {path['title']}",
                f"_{path['subtitle']} — {path['description']}_",
                f"Suggested reading order ({len(group)} essays):\n\n{order}",
            ]
            content = "\n\n".join([*intro, "---", *[essay_markdown(e, 2) for e in group]]) + "\n"
            data = write(f"paths/{path['id']}.md", content)
            manifest_files.append(
                {
                    "path": f"paths/{path['id']}.md",
                    "bytes": len(data),
                    "words": word_count(content),
                    "kind": "path",
                    "label": path["title"],
                }
            )

        zip_path = staging / "askgraham-export.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in entries:
                archive.writestr(name, data)
        zip_bytes = zip_path.stat().st_size
        manifest_files.append(
            {
                "path": "askgraham-export.zip",
                "bytes": zip_bytes,
                "words": 0,
                "kind": "zip",
                "label": "All markdown files (.zip)",
            }
        )

        manifest = {
            "generated": generated,
            "essays": len(essays),
            "words": total_words,
            "source": SOURCE,
            "files": manifest_files,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if target.exists():
            shutil.rmtree(target)
        staging.rename(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        log.exception("export.failed", target=str(target))
        raise

    stats.essays = len(essays)
    stats.words = total_words
    stats.bundles = sum(1 for f in manifest_files if f["kind"] == "bundle")
    stats.paths = sum(1 for f in manifest_files if f["kind"] == "path")
    stats.files = len(manifest_files)
    stats.bytes = sum(f["bytes"] for f in manifest_files)

    log.info("export.complete", path=str(target), **stats.as_dict())
    return stats


__all__ = [
    "SOURCE",
    "ExportStats",
    "collection",
    "decade_of",
    "essay_markdown",
    "export_corpus",
    "fmt_int",
    "front_matter",
    "meta_line",
    "word_count",
]
