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
                    f"phase tags: {stats.phases_written}  "
                    f"paths: {stats.paths_written}"
                )
        except Exception as exc:
            log.exception("cli.ingest_failed")
            raise typer.Exit(code=1) from exc
        finally:
            await db.dispose_engine()

    asyncio.run(main())


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
def stats() -> None:
    """Row counts, to confirm what is actually loaded."""
    configure_logging()

    async def main() -> None:
        from sqlalchemy import func, select

        from core.models import Essay, EssayFootnote, EssayParagraph, PathStep, ReadingPath

        async def count(label: str, model: type[Any]) -> None:
            async with db.get_sessionmaker()() as session:
                n = await session.scalar(select(func.count()).select_from(model))
            typer.echo(f"{label:>18}: {n}")

        try:
            await count("essays", Essay)
            await count("paragraphs", EssayParagraph)
            await count("footnotes", EssayFootnote)
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
