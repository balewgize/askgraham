"""Export formatting.

Only the pure string builders are tested here. The file/zip writing is exercised
by running `cli.py export` against the live database, the same way `snapshot` is.
These guards matter because the `/export` page's labels and the downloaded files
are a public contract.
"""

from rag.export import (
    collection,
    decade_of,
    essay_markdown,
    fmt_int,
    front_matter,
    meta_line,
    word_count,
)


def test_decade_of_groups_by_year() -> None:
    assert decade_of("September 2024") == "2020s"
    assert decade_of("January 2004") == "2000s"
    assert decade_of("1993") == "1990s"


def test_decade_of_undated_is_its_own_bucket() -> None:
    assert decade_of(None) == "undated"
    assert decade_of("undated") == "undated"


def test_fmt_int_matches_us_thousands_separators() -> None:
    assert fmt_int(1234567) == "1,234,567"
    assert fmt_int(0) == "0"


def test_word_count_ignores_whitespace_runs() -> None:
    assert word_count("a\n\n  b\t c ") == 3
    assert word_count("") == 0


def test_meta_line_is_the_expected_one_liner() -> None:
    essay = {
        "date": None,
        "word_count": 1500,
        "reading_time_min": 8,
        "url": "https://example.com/x.html",
    }
    assert meta_line(essay) == (
        "_undated · 1,500 words · 8 min read · [original](https://example.com/x.html)_"
    )


def test_front_matter_quotes_and_escapes() -> None:
    essay = {
        "title": 'The "Best" Idea',
        "slug": "best",
        "date": "1993",
        "url": "https://example.com",
        "word_count": 10,
        "reading_time_min": 1,
    }
    block = front_matter(essay)
    assert block.startswith("---\n")
    assert block.endswith("\n---")
    assert 'title: "The \\"Best\\" Idea"' in block
    assert 'date: "1993"' in block
    assert "slug: best" in block


def test_front_matter_emits_null_for_undated() -> None:
    essay = {
        "title": "X",
        "slug": "x",
        "date": None,
        "url": "u",
        "word_count": 1,
        "reading_time_min": 1,
    }
    assert "date: null" in front_matter(essay)


def test_essay_markdown_includes_notes_only_when_present() -> None:
    base = {
        "title": "T",
        "url": "u",
        "date": None,
        "word_count": 2,
        "reading_time_min": 1,
        "paragraphs": ["one", "two"],
    }
    without = essay_markdown({**base, "footnotes": []}, 1)
    assert without.startswith("# T")
    assert "Notes" not in without

    with_notes = essay_markdown({**base, "footnotes": [{"id": "1", "text": "note"}]}, 1)
    assert "## Notes" in with_notes
    assert "- **[1]** note" in with_notes


def test_collection_starts_at_level_two() -> None:
    essay = {
        "title": "T",
        "url": "u",
        "date": None,
        "word_count": 1,
        "reading_time_min": 1,
        "paragraphs": ["p"],
        "footnotes": [],
    }
    out = collection("Bundle", "subtitle", [essay])
    assert out.startswith("# Bundle\n\n_subtitle_\n\n---\n\n")
    assert "## T" in out
    assert out.endswith("\n")
