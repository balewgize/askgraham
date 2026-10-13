"""Ingest logic that does not need a database.

These are the functions the idempotency guarantee rests on, so they are tested
directly. If `essay_content_hash` changed shape, every re-run would rewrite the
whole corpus and the skip path would silently stop working.
"""

import json
from pathlib import Path

import pytest

from core.errors import ValidationError
from rag.ingest import (
    date_key,
    essay_content_hash,
    essay_meta_hash,
    read_essay_files,
)

# ── date_key ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("September 2024", (2024, 9)),
        ("January 2004", (2004, 1)),
        ("December 1999", (1999, 12)),
        # Case-insensitive on purpose: PG used inconsistent capitalisation.
        ("january 2020", (2020, 1)),
        # Year only, as on the older essays.
        ("1993", (1993, None)),
        # A year buried in a longer string.
        ("Spring 1995", (1995, None)),
        (None, (None, None)),
        ("", (None, None)),
        ("undated", (None, None)),
    ],
)
def test_date_key(raw: str | None, expected: tuple[int | None, int | None]) -> None:
    assert date_key(raw) == expected


def test_date_key_undated_sorts_before_real_dates() -> None:
    """Undated essays must land at the end of a DESC sort, not the start."""
    assert date_key(None) == (None, None)


# ── hashes ────────────────────────────────────────────────────────────


def test_content_hash_ignores_metadata() -> None:
    """Only prose edits should count as a body change."""
    a = {"slug": "x", "title": "Old", "date": "2001", "paragraphs": ["one"]}
    b = {"slug": "x", "title": "New", "date": "2020", "paragraphs": ["one"]}
    assert essay_content_hash(a) == essay_content_hash(b)


def test_content_hash_changes_with_paragraphs() -> None:
    a = {"paragraphs": ["one"]}
    b = {"paragraphs": ["two"]}
    assert essay_content_hash(a) != essay_content_hash(b)


def test_content_hash_is_sensitive_to_paragraph_order() -> None:
    """Reordering paragraphs is a real change; swapping them must not collide."""
    a = {"paragraphs": ["one", "two"]}
    b = {"paragraphs": ["two", "one"]}
    assert essay_content_hash(a) != essay_content_hash(b)


def test_meta_hash_ignores_body() -> None:
    a = {"slug": "x", "title": "T", "paragraphs": ["one"]}
    b = {"slug": "x", "title": "T", "paragraphs": ["two"]}
    assert essay_meta_hash(a) == essay_meta_hash(b)


def test_meta_hash_changes_with_title() -> None:
    a = {"slug": "x", "title": "One"}
    b = {"slug": "x", "title": "Two"}
    assert essay_meta_hash(a) != essay_meta_hash(b)


def test_hashes_are_hex_sha256() -> None:
    h = essay_content_hash({"paragraphs": ["x"]})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_content_hash_handles_unicode() -> None:
    """PG essays contain curly quotes and em dashes."""
    h = essay_content_hash({"paragraphs": ["“quoted” — yes"]})
    assert len(h) == 64


# ── corpus reading ────────────────────────────────────────────────────


def test_read_essay_files_rejects_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="no essays directory"):
        read_essay_files(tmp_path)


def test_read_essay_files_rejects_invalid_json(tmp_path: Path) -> None:
    essays = tmp_path / "essays"
    essays.mkdir()
    (essays / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValidationError, match="not valid JSON"):
        read_essay_files(tmp_path)


def test_read_essay_files_rejects_essay_without_slug(tmp_path: Path) -> None:
    essays = tmp_path / "essays"
    essays.mkdir()
    (essays / "anon.json").write_text(json.dumps({"title": "No slug"}), encoding="utf-8")
    with pytest.raises(ValidationError, match="no slug"):
        read_essay_files(tmp_path)


def test_read_essay_files_reads_real_corpus() -> None:
    """The committed corpus must stay ingestible."""
    from config import settings

    payloads = read_essay_files(settings.data_dir)
    assert len(payloads) == 233
    slugs = {p["slug"] for p in payloads}
    assert "say" in slugs
    assert len(slugs) == len(payloads), "duplicate slugs in corpus"


def test_read_essay_files_ignores_non_json(tmp_path: Path) -> None:
    essays = tmp_path / "essays"
    essays.mkdir()
    (essays / "a.json").write_text(json.dumps({"slug": "a"}), encoding="utf-8")
    (essays / "README.md").write_text("ignore me", encoding="utf-8")
    assert [p["slug"] for p in read_essay_files(tmp_path)] == ["a"]
