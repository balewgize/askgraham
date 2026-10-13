"""Batch commands for the backend.

Run as `uv run python cli.py <command>`. Each command is idempotent so it can be
re-run freely in CI or after re-scraping the corpus.
"""

import asyncio
from pathlib import Path
from typing import Any

import typer

from config import settings
from core import db
from core.logging_config import configure_logging, log
from rag.ingest import ingest_corpus

app = typer.Typer(
    help="askgraham backend commands.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def ingest(
    data_dir: Path | None = typer.Option(
        None, "--data-dir", help="Corpus directory. Defaults to the repo's data/."
    ),
) -> None:
    """Load the essay corpus into Postgres. Skips unchanged content."""
    configure_logging()

    async def main() -> None:
        # One event loop for the whole command. The engine and its asyncpg
        # connections are bound to the loop that created them, so disposing in a
        # second asyncio.run() raises "Event loop is closed".
        try:
            async with db.session_scope() as session:
                stats = await ingest_corpus(session, data_dir)
                typer.echo(
                    f"essays: {stats.essays_written} written, "
                    f"{stats.essays_skipped} unchanged, {stats.essays_seen} seen\n"
                    f"paragraphs: {stats.paragraphs_written}  "
                    f"footnotes: {stats.footnotes_written}  "
                    f"phase tags: {stats.phase_tags_written}  "
                    f"paths: {stats.paths_written}"
                )
        except Exception as exc:
            log.exception("cli.ingest_failed")
            raise typer.Exit(code=1) from exc
        finally:
            await db.dispose_engine()

    asyncio.run(main())


@app.command()
def scrape(
    slugs: str | None = typer.Option(
        None, "--slugs", help="Comma-separated slugs. Defaults to the whole catalogue."
    ),
    limit: int | None = typer.Option(None, "--limit", help="Only the first N essays."),
    data_dir: Path | None = typer.Option(
        None, "--data-dir", help="Corpus directory. Defaults to the repo's data/."
    ),
) -> None:
    """Fetch the catalogue from paulgraham.com into data/.

    Polite by design: one request every 1.5s, and a descriptive User-Agent.
    """
    configure_logging()
    from rag.scrape import scrape_catalog

    stats = scrape_catalog(
        data_dir or settings.data_dir,
        slugs=[s.strip() for s in slugs.split(",")] if slugs else None,
        limit=limit,
    )
    typer.echo(
        f"index: {stats.index_entries} essays\n"
        f"wrote: {stats.written}/{stats.requested}  ({stats.words:,} words)"
    )
    if stats.skipped:
        typer.echo(f"skipped: {', '.join(stats.skipped)}", err=True)


@app.command()
def classify(
    force: bool = typer.Option(False, "--force", help="Ignore the cache and redo everything."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would run. No API calls."),
    limit: int | None = typer.Option(None, "--limit", help="Classify at most N essays."),
    push: bool = typer.Option(True, "--push/--no-push", help="Also write results into Postgres."),
    data_dir: Path | None = typer.Option(
        None, "--data-dir", help="Corpus directory. Defaults to the repo's data/."
    ),
) -> None:
    """Tag essays by startup stage. Only pays for essays whose text changed.

    Exits non-zero if any essay failed, so a CI run cannot mistake a partial
    result for a complete one.
    """
    configure_logging()
    from llm.classify import ClassifyStats, classify_essays
    from rag.ingest import IngestStats, upsert_essay_phases

    source = data_dir or settings.data_dir
    outcome: ClassifyStats | None = None

    async def main() -> None:
        nonlocal outcome
        try:
            outcome = await classify_essays(source, limit=limit, force=force, dry_run=dry_run)
            if dry_run:
                typer.echo(f"dry run — {outcome.attempted} would be classified, nothing written")
                return
            typer.echo(
                f"model: {outcome.model}\n"
                f"{outcome.total} essays · {outcome.cached} cached · "
                f"{outcome.classified} classified · {len(outcome.failures)} failed"
            )
            if push:
                # Reuses the ingest upsert rather than a second code path, so a
                # tag written here cannot drift from one written by `ingest`.
                async with db.session_scope() as session:
                    stats = IngestStats()
                    await upsert_essay_phases(session, source, stats)
                typer.echo(f"pushed {stats.phase_tags_written} phase tags to Postgres")
        except Exception as exc:
            log.exception("cli.classify_failed")
            raise typer.Exit(code=1) from exc
        finally:
            await db.dispose_engine()

    asyncio.run(main())

    if outcome and outcome.failures:
        typer.echo(f"{len(outcome.failures)} failed — rerun to retry them", err=True)
        raise typer.Exit(code=1)


@app.command()
def index(
    force: bool = typer.Option(False, "--force", help="Re-embed everything, ignoring hashes."),
    limit: int | None = typer.Option(None, "--limit", help="Index at most N essays."),
) -> None:
    """Chunk and embed the corpus into Postgres. Re-embeds only changed chunks."""
    configure_logging()

    async def main() -> None:
        from rag.retrieval import index_chunks

        try:
            async with db.session_scope() as session:
                stats = await index_chunks(session, force=force, limit=limit)
                typer.echo(
                    f"essays: {stats.essays_seen} seen, {stats.essays_indexed} indexed, "
                    f"{stats.essays_skipped} unchanged\n"
                    f"chunks: {stats.chunks_written} written, {stats.chunks_skipped} unchanged "
                    f"({stats.tokens:,} tokens)\n"
                    f"elapsed: {stats.elapsed_s:.1f}s"
                )
        except Exception as exc:
            log.exception("cli.index_failed")
            raise typer.Exit(code=1) from exc
        finally:
            await db.dispose_engine()

    asyncio.run(main())


@app.command()
def paths(
    only: str | None = typer.Option(None, "--only", help="Regenerate a single path by id."),
    force: bool = typer.Option(False, "--force", help="Ignore the cache and regenerate."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would run. No API calls."),
    push: bool = typer.Option(True, "--push/--no-push", help="Also write results into Postgres."),
    data_dir: Path | None = typer.Option(
        None, "--data-dir", help="Corpus directory. Defaults to the repo's data/."
    ),
) -> None:
    """Curate reading paths. Only pays for specs whose intent changed."""
    configure_logging()
    from llm.paths import PathsStats, generate_paths
    from rag.ingest import IngestStats, upsert_paths

    source = data_dir or settings.data_dir
    outcome: PathsStats | None = None

    async def main() -> None:
        nonlocal outcome
        try:
            outcome = await generate_paths(source, only=only, force=force, dry_run=dry_run)
            if dry_run:
                typer.echo(f"dry run — {outcome.selected - outcome.cached} would be generated")
                return
            typer.echo(
                f"model: {outcome.model}\n"
                f"{outcome.total} paths · {outcome.selected} selected · "
                f"{outcome.generated} generated · {len(outcome.failures)} failed"
            )
            if push:
                async with db.session_scope() as session:
                    stats = IngestStats()
                    await upsert_paths(session, source, stats)
                typer.echo(
                    f"pushed {stats.paths_written} paths, "
                    f"{stats.paths_skipped} unchanged to Postgres"
                )
        except Exception as exc:
            log.exception("cli.paths_failed")
            raise typer.Exit(code=1) from exc
        finally:
            await db.dispose_engine()

    asyncio.run(main())

    if outcome and outcome.failures:
        typer.echo(f"{len(outcome.failures)} failed — rerun to retry them", err=True)
        raise typer.Exit(code=1)


@app.command()
def snapshot(
    out_dir: Path | None = typer.Option(
        None, "--out-dir", help="Destination. Defaults to frontend/snapshot."
    ),
) -> None:
    """Write the frontend's build-time corpus from Postgres."""
    configure_logging()

    async def main() -> None:
        from rag.snapshot import export_snapshot

        try:
            async with db.session_scope() as session:
                stats = await export_snapshot(session, out_dir)
                typer.echo(
                    f"essays: {stats.essays} ({stats.words:,} words)\n"
                    f"paragraphs: {stats.paragraphs}  footnotes: {stats.footnotes}  "
                    f"phase tags: {stats.phases}\n"
                    f"paths: {stats.paths}  steps: {stats.path_steps}"
                )
        except Exception as exc:
            log.exception("cli.snapshot_failed")
            raise typer.Exit(code=1) from exc
        finally:
            await db.dispose_engine()

    asyncio.run(main())


@app.command()
def export(
    out_dir: Path | None = typer.Option(
        None, "--out-dir", help="Destination. Defaults to frontend/public/export."
    ),
) -> None:
    """Write the downloadable corpus bundles the /export page links to."""
    configure_logging()

    async def main() -> None:
        from rag.export import export_corpus

        try:
            async with db.session_scope() as session:
                stats = await export_corpus(session, out_dir)
            typer.echo(
                f"essays: {stats.essays} ({stats.words:,} words) · "
                f"{stats.files} files · {stats.bytes / 1_048_576:.1f} MB"
            )
        except Exception as exc:
            log.exception("cli.export_failed")
            raise typer.Exit(code=1) from exc
        finally:
            await db.dispose_engine()

    asyncio.run(main())


@app.command()
def stats() -> None:
    """Row counts, to confirm what is actually loaded."""
    configure_logging()

    async def main() -> None:
        from sqlalchemy import func, select

        from core.models import (
            Chunk,
            Essay,
            EssayFootnote,
            EssayParagraph,
            PathStep,
            ReadingPath,
        )

        async def count(label: str, model: type[Any]) -> None:
            async with db.get_sessionmaker()() as session:
                n = await session.scalar(select(func.count()).select_from(model))
            typer.echo(f"{label:>18}: {n}")

        try:
            await count("essays", Essay)
            await count("paragraphs", EssayParagraph)
            await count("footnotes", EssayFootnote)
            await count("chunks (indexed)", Chunk)
            await count("reading paths", ReadingPath)
            await count("path steps", PathStep)
        finally:
            await db.dispose_engine()

    asyncio.run(main())


@app.command()
def env() -> None:
    """Print the resolved settings. First thing to check when something is wrong."""
    configure_logging()
    typer.echo(f"environment   : {settings.environment}")
    typer.echo(f"database_url  : {_redact(settings.database_url)}")
    typer.echo(f"data_dir      : {settings.data_dir} (exists={settings.data_dir.is_dir()})")
    typer.echo(f"log_level     : {settings.log_level}")
    typer.echo(f"llm configured: {bool(settings.openrouter_api_key)}")


def _redact(url: str) -> str:
    """Hide the password in a database URL before it reaches a log or terminal."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" not in creds:
        return url
    user, _ = creds.split(":", 1)
    return f"{scheme}://{user}:***@{host}"


if __name__ == "__main__":
    app()
