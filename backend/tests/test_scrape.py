"""Scraper parsing logic.

These run against saved HTML fixtures rather than the network, so they are fast
and deterministic. The fixtures capture the four ways PG's markup broke the
naive implementation, and each test names the page it came from.

The end-to-end proof that this port matches the TypeScript it replaces is a
fixture-diff against `data/essays/`; see `test_scrape_matches_committed_corpus`.
Parsing is exercised here, fetching is not.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from rag.scrape import (
    parse_index,
    parse_inline_essay,
    parse_notes_page,
    text_with_breaks,
)

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def fixture(name: str) -> str:
    path = FIXTURES / f"{name}.html"
    if not path.exists():
        pytest.skip(f"fixture {name}.html not recorded")
    return path.read_text(encoding="utf-8")


# ── text extraction ───────────────────────────────────────────────────


def test_br_becomes_whitespace() -> None:
    """Without this, "July 2009<br><br>Now..." reads "July 2009Now...".

    That glues the date onto the first sentence and hides it entirely, which is
    why the date is missing from every essay if this breaks.
    """
    assert text_with_breaks("July 2009<br><br>Now the story") == "July 2009 Now the story"


def test_comments_are_excluded() -> None:
    """cheerio's .text() skips comments; BeautifulSoup's get_text() does not.

    PG leaves commented-out editorial notes in his markup (say.html,
    polls.html). Emitting them adds phantom paragraphs and inflates word counts.
    """
    html = "January 2004<br/><br/><!--<i>(This essay is about heresy)</i>-->Real opening"
    assert text_with_breaks(html) == "January 2004 Real opening"


def test_comments_do_not_leak_into_inner_html() -> None:
    """Regression: joining str(child) dropped the <!-- --> wrapper.

    `str()` on a Comment returns only its text, promoting commented-out markup
    to visible content before any filter could remove it.
    """
    from rag.scrape import _inner_html, _soup

    tag = _soup("<font size='2'>a<!--b-->c</font>").find("font")
    assert tag is not None
    assert "<!--" in _inner_html(tag)


def test_whitespace_is_collapsed() -> None:
    assert text_with_breaks("a\n\n  b\t c") == "a b c"


# ── index ─────────────────────────────────────────────────────────────


def test_parse_index_finds_essays() -> None:
    entries = parse_index(fixture("articles"))
    assert len(entries) > 200
    assert all(e.slug and e.url.startswith("https://www.paulgraham.com/") for e in entries)


def test_parse_index_deduplicates_slugs() -> None:
    entries = parse_index(fixture("articles"))
    slugs = [e.slug for e in entries]
    assert len(slugs) == len(set(slugs))


def test_parse_index_excludes_navigation_links() -> None:
    """Nav links lack the orange bullet gif and must not be treated as essays.

    `rss` is deliberately not in this list: PG added it to the article index
    itself, so it is a legitimate (if stub-like) entry.
    """
    entries = parse_index(fixture("articles"))
    slugs = {e.slug for e in entries}
    for nav in ("index", "books", "bio", "faq", "articles"):
        assert nav not in slugs


def test_parse_index_raises_when_markup_changes() -> None:
    """A silent zero would wipe the catalogue; fail loudly instead."""
    with pytest.raises(ValueError, match="0 essays"):
        parse_index("<html><body><td><a href='say.html'>Say</a></td></body></html>")


# ── essay pages ───────────────────────────────────────────────────────


def test_say_comment_does_not_become_a_paragraph() -> None:
    """say.html has a commented-out editorial note which must stay invisible."""
    essay, _ = parse_inline_essay("say", "https://www.paulgraham.com/say.html", fixture("say"))
    assert essay.date == "January 2004"
    assert len(essay.paragraphs) == 90
    assert essay.word_count == 5396
    assert not essay.paragraphs[0].startswith("(This essay is about heresy")
    assert essay.paragraphs[0].startswith("Have you ever seen an old photo")


def test_say_footnotes_come_from_the_separate_notes_page() -> None:
    """say's footnotes are not inline; they live on saynotes.html.

    Parsing the essay alone must therefore yield no footnotes plus a notes href,
    and combining the two must produce all 17.
    """
    essay, notes_href = parse_inline_essay(
        "say", "https://www.paulgraham.com/say.html", fixture("say")
    )
    assert notes_href == "saynotes.html"
    assert essay.footnotes == []
    essay.footnotes = parse_notes_page(fixture("saynotes"))
    assert [f["id"] for f in essay.footnotes] == [str(i) for i in range(1, 18)]


def test_ramenprofitable_unclosed_font() -> None:
    """Regression: the body <font> is never closed.

    lxml auto-closes it after ~1.9k chars and the essay silently truncates to a
    seventh of its text; html5lib/parse5 keep it open. This is the test that
    fails if _PARSER drifts back to a non-spec parser.
    """
    essay, _ = parse_inline_essay(
        "ramenprofitable",
        "https://www.paulgraham.com/ramenprofitable.html",
        fixture("ramenprofitable"),
    )
    assert len(essay.paragraphs) == 22, "body truncated — parser closed <font> early"
    assert essay.word_count == 1426
    assert len(essay.footnotes) == 3


def test_ramenprofitable_strips_in_body_ad_table() -> None:
    """The YC banner is a <table> inside the body and must not reach the reader."""
    essay, _ = parse_inline_essay(
        "ramenprofitable",
        "https://www.paulgraham.com/ramenprofitable.html",
        fixture("ramenprofitable"),
    )
    joined = " ".join(essay.paragraphs)
    assert "Get funded by Y Combinator" not in joined


def test_progbot_year_only_date() -> None:
    """progbot is dated "1993" with no month, and must keep its opening prose."""
    essay, _ = parse_inline_essay(
        "progbot", "https://www.paulgraham.com/progbot.html", fixture("progbot")
    )
    assert essay.date == "1993"
    assert len(essay.paragraphs) == 14
    assert essay.word_count == 918


def test_fix_unclosed_p_tags() -> None:
    """fix.html has unclosed <p> tags that split content across sibling fonts."""
    essay, _ = parse_inline_essay("fix", "https://www.paulgraham.com/fix.html", fixture("fix"))
    assert len(essay.paragraphs) == 27
    assert essay.word_count == 262


def test_saynotes_separate_notes_page() -> None:
    """saynotes.html is Windows-1252 and holds footnotes off the essay page."""
    notes = parse_notes_page(fixture("saynotes"))
    assert len(notes) > 0
    assert all(set(n) == {"id", "text"} for n in notes)
    # Ids are normalised to integers-as-strings ("01" -> "1").
    assert all(n["id"] == str(int(n["id"])) for n in notes)


def test_footnotes_are_addressed_by_marker() -> None:
    """Ids are normalised to integers-as-strings ("01" -> "1")."""
    markers = [f["id"] for f in parse_notes_page(fixture("saynotes"))]
    assert markers == [str(i) for i in range(1, 18)]


def test_reading_time_is_at_least_one_minute() -> None:
    essay, _ = parse_inline_essay("fix", "https://www.paulgraham.com/fix.html", fixture("fix"))
    assert essay.reading_time_min >= 1
    assert essay.reading_time_min == max(1, -(-essay.word_count // 200))


def test_paragraphs_are_non_empty_and_trimmed() -> None:
    essay, _ = parse_inline_essay("say", "https://www.paulgraham.com/say.html", fixture("say"))
    assert all(p == p.strip() and p for p in essay.paragraphs)


# ── corpus-wide contract ──────────────────────────────────────────────


def _normalise_c1(text: str) -> str:
    """Map Windows-1252 C1 control characters to their real characters.

    The committed corpus was decoded with Latin-1 semantics, so it holds U+0097
    where byte 0x97 appears (should be an em dash) and U+0092 where byte 0x92
    appears (should be a curly apostrophe). The scraper now decodes those bytes
    as Windows-1252 and produces the correct characters. Normalising both sides
    keeps this test measuring *parsing* rather than the corpus's encoding debt.
    """
    out = []
    for ch in text:
        if 0x80 <= ord(ch) <= 0x9F:
            try:
                out.append(bytes([ord(ch)]).decode("windows-1252"))
                continue
            except UnicodeDecodeError:
                pass
        out.append(ch)
    return "".join(out)


def _normalise_essay(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["paragraphs"] = [_normalise_c1(p) for p in payload["paragraphs"]]
    payload["footnotes"] = [{**f, "text": _normalise_c1(f["text"])} for f in payload["footnotes"]]
    return payload


def test_scrape_matches_committed_corpus() -> None:
    """Every recorded fixture must reproduce the committed JSON.

    The committed corpus is a valid reference because a fresh run of the
    TypeScript scraper reproduces it byte-for-byte, and this port was diffed
    against that scraper on the same live pages for all 233 essays.
    """
    from config import settings

    checked = 0
    for path in sorted(FIXTURES.glob("*.html")):
        if path.name == "articles.html" or path.name.endswith("notes.html"):
            continue
        slug = path.name.removesuffix(".html")
        want_path = settings.data_dir / "essays" / f"{slug}.json"
        if not want_path.exists():
            continue

        html = path.read_text(encoding="utf-8")
        essay, notes_href = parse_inline_essay(slug, "", html)
        # Replicate the scraper: footnotes may live on a separate notes page.
        if notes_href:
            notes_fixture = FIXTURES / notes_href
            if notes_fixture.exists():
                essay.footnotes = parse_notes_page(notes_fixture.read_text(encoding="utf-8"))
        want = json.loads(want_path.read_text(encoding="utf-8"))

        got = _normalise_essay(essay.as_dict())
        got["url"] = want["url"]  # set from the index entry, not parsing
        assert got == _normalise_essay(want), f"{path.name} differs"
        checked += 1

    assert checked >= 5, f"expected at least 5 fixtures compared, got {checked}"
