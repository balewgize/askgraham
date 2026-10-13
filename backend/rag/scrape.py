"""Scrape Paul Graham's essay catalog into `data/`.

    uv run python cli.py scrape                    # whole catalog
    uv run python cli.py scrape --slugs say,fix    # a few, for spot checks
    uv run python cli.py scrape --limit 5

Ported from `frontend/scripts/scrape-essays.ts`. The heuristics below are not
guesswork — each one was derived by inspecting real pages that broke the naive
approach, and the comments record which page and why. PG's markup is
hand-written HTML from 1993 onward: unclosed tags, tables used for layout, and
Windows-1252 encodings on the oldest files.

A port of this file is only trustworthy if its output is diffed against the
committed corpus, which is what `tests/test_scrape.py` does for the awkward
slugs (progbot, fix, ramenprofitable, say).
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag
from bs4.element import Comment

from core.logging_config import log

BASE = "https://www.paulgraham.com"
INDEX_URL = f"{BASE}/articles.html"
USER_AGENT = (
    "askgraham-scraper/0.1 "
    "(personal learning project; reading tool; contact: owner of this local project)"
)
REQUEST_DELAY_S = 1.5
REQUEST_TIMEOUT_S = 30.0

# HTML5-spec-compliant parsing, matching cheerio's parse5.
#
# This is not a preference. PG's markup contains unclosed <font> tags, and the
# parsers disagree about how to close them: on ramenprofitable.html lxml
# auto-closes the body <font> after 1.9k characters, while parse5 (and
# html5lib) keeps it open for 10.5k. The body-selection heuristic counts
# substantial <font> elements, so the wrong tree shape silently truncates the
# essay to a seventh of its text and reports a plausible-looking word count.
_PARSER = "html5lib"

DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October"
    r"|November|December)\s+(19\d{2}|20\d{2})\b"
)
NOTES_MARKER_RE = re.compile(r"<b>\s*Notes\s*</b>", re.IGNORECASE)
THANKS_MARKER_RE = re.compile(r"<b>\s*Thanks\s*</b>", re.IGNORECASE)
# Notes may link to a relative ("saynotes.html") or an absolute URL.
NOTES_PAGE_RE = re.compile(
    r'href="(?:https?://www\.paulgraham\.com/)?([a-z0-9_-]*notes\.html)"', re.IGNORECASE
)
_LEAD_MONTH_RE = re.compile(
    r"^\s*(January|February|March|April|May|June|July|August|September|October"
    r"|November|December)\s+(19\d{2}|20\d{2})\b"
)
_ANCHOR_FN_RE = re.compile(r"^f(\d+)n?$", re.IGNORECASE)
_LEAD_BRACKET_RE = re.compile(r"^\[\s*(\d+)\s*\]")
_SEPARATOR_RE = re.compile(r"^\*\s*\*\s*\*$")
_SLUG_HREF_RE = re.compile(r"^[a-z0-9_-]+\.html$", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_DOUBLE_BR_RE = re.compile(r"<br\s*/?>\s*<br\s*/?>", re.IGNORECASE)
_P_TAG_RE = re.compile(r"</?p\b[^>]*>", re.IGNORECASE)
_TO_ESSAY_RE = re.compile(r"\(to\s*<a", re.IGNORECASE)
_REDDIT_BULLET = 'img[src*="the-reddits-2.gif"]'
_ESSAY_COLUMN = 'td[width="435"], td[width="374"]'
_BODY_FONT = 'font[size="2"]'


@dataclass
class IndexEntry:
    title: str
    url: str
    slug: str


@dataclass
class Essay:
    slug: str
    title: str
    url: str
    date: str | None
    word_count: int
    reading_time_min: int
    paragraphs: list[str] = field(default_factory=list)
    footnotes: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "url": self.url,
            "date": self.date,
            "word_count": self.word_count,
            "reading_time_min": self.reading_time_min,
            "paragraphs": self.paragraphs,
            "footnotes": self.footnotes,
        }

    def index_row(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "date": self.date,
            "word_count": self.word_count,
            "reading_time_min": self.reading_time_min,
        }


@dataclass
class ScrapeStats:
    index_entries: int = 0
    requested: int = 0
    written: int = 0
    skipped: list[str] = field(default_factory=list)
    words: int = 0


# ── fetching ──────────────────────────────────────────────────────────


def fetch_html(client: httpx.Client, url: str) -> str:
    """Fetch a page, falling back to Windows-1252 for the oldest files.

    Most pages are UTF-8. Early-2000s pages (e.g. saynotes.html) are
    Windows-1252, and decoding those as UTF-8 raises rather than mojibakes,
    which is what makes a strict-first decode safe.
    """
    response = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S)
    response.raise_for_status()
    raw = response.content
    try:
        return raw.decode("utf-8")  # strict on purpose
    except UnicodeDecodeError:
        return raw.decode("windows-1252")


# ── small helpers ─────────────────────────────────────────────────────


def _inner_html(node: Tag) -> str:
    """Inner HTML of a node, matching cheerio's `.html()`.

    `decode_contents()` rather than joining `str(child)`: `str()` on a `Comment`
    returns only the comment's *text*, silently dropping the `<!--...-->`
    wrapper and promoting commented-out markup to visible content. PG leaves
    editorial notes in comments (say.html, polls.html), so that turned them into
    essay paragraphs.
    """
    return node.decode_contents()


def _soup(fragment: str) -> BeautifulSoup:
    return BeautifulSoup(fragment, _PARSER)


def text_with_breaks(fragment: str) -> str:
    """Text of an HTML fragment with <br> treated as whitespace.

    `get_text()` concatenates across <br>, so "July 2009<br><br>Now..." would
    read "July 2009Now..." and hide the date. Converting <br> to a space first
    is what makes date extraction work at all.

    Comments must be removed first. cheerio's `.text()` skips them;
    BeautifulSoup's `get_text()` does not, because `Comment` subclasses
    `NavigableString`. PG leaves commented-out editorial notes in his markup
    (say.html, polls.html), and without this they are emitted as essay text.
    """
    spaced = _BR_RE.sub(" ", fragment)
    soup = _soup(spaced)
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    return re.sub(r"\s+", " ", soup.get_text()).strip()


def _blocks_to_footnotes(blocks: list[str]) -> list[dict[str, str]]:
    """Group split blocks into footnotes.

    A block with no leading `[N]` and no `fN` anchor is a continuation of the
    previous footnote — that happens when multi-paragraph footnotes (recipes,
    code) are split by the same <br><br> boundary as the body.
    """
    footnotes: list[dict[str, str]] = []
    for block in blocks:
        if THANKS_MARKER_RE.search(block):
            break
        text = text_with_breaks(block)
        if not text:
            continue
        anchor = _soup(block).find("a", attrs={"name": True})
        anchor_match = _ANCHOR_FN_RE.match(str(anchor.get("name", ""))) if anchor else None
        lead_match = _LEAD_BRACKET_RE.match(text)
        marker = (anchor_match.group(1) if anchor_match else None) or (
            lead_match.group(1) if lead_match else None
        )
        if marker:
            clean = _LEAD_BRACKET_RE.sub("", text).strip()
            if clean:
                footnotes.append({"id": str(int(marker)), "text": clean})
        elif footnotes:
            footnotes[-1]["text"] += f"\n\n{text}"
    return footnotes


# ── index ─────────────────────────────────────────────────────────────


def parse_index(html: str) -> list[IndexEntry]:
    """Essay rows only.

    They are marked by the orange-square bullet gif; the nav links at the top of
    the page are not, and would otherwise be scraped as essays.
    """
    soup = _soup(html)
    entries: list[IndexEntry] = []
    seen: set[str] = set()

    for td in soup.find_all("td"):
        if not td.select(_REDDIT_BULLET):
            continue
        for anchor in td.select('a[href$=".html"]'):
            href = str(anchor.get("href", "")).strip()
            title = re.sub(r"\s+", " ", anchor.get_text()).strip()
            if not _SLUG_HREF_RE.match(href) or not title:
                continue
            slug = re.sub(r"\.html$", "", href, flags=re.IGNORECASE)
            if slug in seen:
                continue
            seen.add(slug)
            entries.append(IndexEntry(title=title, url=f"{BASE}/{href}", slug=slug))

    if not entries:
        raise ValueError("index parse found 0 essays — markup changed?")
    return entries


# ── essay body ────────────────────────────────────────────────────────


def _extract_date(column_text: str) -> str | None:
    match = DATE_RE.search(column_text)
    if match:
        return match.group(0)

    # Year-only dates (progbot: "1993 ..."). Restricted to the head so a body
    # year like "In 1960, ..." cannot false-positive.
    head = column_text[:300]
    year_only = re.match(r"^\s*(19\d{2}|20\d{2})\b", head) or re.search(
        r"\b(19\d{2}|20\d{2})\b", head
    )
    # `date` may legitimately be None: fix, noop and the rss stub are undated.
    return year_only.group(0).strip() if year_only else None


def _leading_date_consumed(text: str) -> str | None:
    """Strip a leading date from the first paragraph. None if there wasn't one."""
    month = _LEAD_MONTH_RE.match(text)
    # Only strip a year-only lead when it is parenthetical or the whole block;
    # otherwise prose like "1993 was the year..." would lose its opening.
    year = re.match(r"^\s*(19\d{2}|20\d{2})\s*\(", text) or (
        re.match(r"^\s*(19\d{2}|20\d{2})\b", text) if len(text) < 30 else None
    )
    lead = month or year
    if not lead:
        return None

    rest = re.sub(r"^\)?\s*", "", text[lead.end() :]).strip()
    if not rest:
        return ""
    if year:
        # Keep the opening paren that the parenthetical form implies.
        return f"({rest}" if "(" in lead.group(0) else rest
    return rest


def parse_inline_essay(slug: str, url: str, html: str) -> tuple[Essay, str | None]:
    """Parse one essay page. Returns the essay and any separate notes-page href."""
    soup = _soup(html)

    title_node = soup.find("title")
    title = re.sub(r"\s+", " ", title_node.get_text()).strip() if title_node else ""
    if not title:
        raise ValueError("no <title>")

    # Main column is usually td width 435; one outlier (polls) uses 374. The
    # richest such td is the essay column — translation and footer tds are tiny.
    best: Tag | None = None
    best_len = -1
    for td in soup.select(_ESSAY_COLUMN):
        length = len(text_with_breaks(_inner_html(td)))
        if length > best_len:
            best_len = length
            best = td
    if best is None:
        raise ValueError("essay column not found")

    column_text = text_with_breaks(_inner_html(best))
    date = _extract_date(column_text)

    # Body is normally a single substantial <font size=2>. Unclosed <p> tags
    # (fix, founders, rootsoflisp) split the content across sibling fonts, and
    # then the whole column is the right answer instead.
    fonts = [f for f in best.select(_BODY_FONT) if len(text_with_breaks(_inner_html(f))) > 200]
    if len(fonts) == 1:
        body = fonts[0]
        # Strip in-body ad tables (e.g. the YC banner on ramenprofitable) but
        # keep the surrounding text flow.
        for table in body.find_all("table"):
            table.decompose()
        raw = _inner_html(body)
    else:
        for table in best.find_all("table"):
            table.decompose()
        raw = _inner_html(best)

    # Normalize <p> paragraph markup to the same boundary the splitter uses.
    raw = _P_TAG_RE.sub("<br><br>", raw)
    blocks = _DOUBLE_BR_RE.split(raw)

    notes_idx = next((i for i, b in enumerate(blocks) if NOTES_MARKER_RE.search(b)), -1)
    notes_page_href: str | None = None
    if notes_idx >= 0:
        match = NOTES_PAGE_RE.search(blocks[notes_idx])
        if match:
            notes_page_href = match.group(1)

    body_end = notes_idx if notes_idx >= 0 else len(blocks)
    paragraphs: list[str] = []
    for block in blocks[:body_end]:
        if THANKS_MARKER_RE.search(block):
            continue
        text = text_with_breaks(block)
        if not text or _SEPARATOR_RE.match(text):
            continue
        if not paragraphs:
            stripped = _leading_date_consumed(text)
            if stripped is not None:
                if stripped:
                    paragraphs.append(stripped)
                continue
        paragraphs.append(text)

    if not paragraphs:
        raise ValueError("0 body paragraphs extracted")

    footnotes: list[dict[str, str]] = []
    if notes_idx >= 0 and not notes_page_href:
        footnotes = _blocks_to_footnotes(blocks[notes_idx + 1 :])

    words = len(" ".join(paragraphs).split())
    essay = Essay(
        slug=slug,
        title=title,
        url=url,
        date=date,
        word_count=words,
        reading_time_min=max(1, -(-words // 200)),  # ceil, matching Math.ceil
        paragraphs=paragraphs,
        footnotes=footnotes,
    )
    return essay, notes_page_href


def parse_notes_page(html: str) -> list[dict[str, str]]:
    """Footnotes that live on their own page (e.g. saynotes.html)."""
    soup = _soup(html)
    fonts = soup.select(f'td[width="435"] {_BODY_FONT}')
    node: Tag | BeautifulSoup = fonts[0] if fonts else soup
    raw = _inner_html(node) if isinstance(node, Tag) else str(soup)
    blocks = _DOUBLE_BR_RE.split(raw)
    # Drop the "(to Essay)" back-link header if present.
    filtered = [b for b in blocks if not _TO_ESSAY_RE.search(b)]
    return _blocks_to_footnotes(filtered)


# ── orchestration ─────────────────────────────────────────────────────


def scrape_catalog(
    data_dir: Path,
    slugs: list[str] | None = None,
    limit: int | None = None,
) -> ScrapeStats:
    """Fetch the catalog and write `data/essays/*.json` plus `data/index.json`."""
    stats = ScrapeStats()
    essays_dir = data_dir / "essays"
    essays_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(follow_redirects=True) as client:
        log.info("scrape.index", url=INDEX_URL)
        entries = parse_index(fetch_html(client, INDEX_URL))
        stats.index_entries = len(entries)
        log.info("scrape.index_parsed", count=len(entries))

        selected = entries
        if slugs:
            wanted = set(slugs)
            selected = [e for e in entries if e.slug in wanted]
            missing = sorted(wanted - {e.slug for e in selected})
            if missing:
                log.warning("scrape.slugs_not_in_index", slugs=missing)
        elif limit and limit > 0:
            selected = entries[:limit]

        stats.requested = len(selected)
        rows: list[dict[str, Any]] = []

        for i, entry in enumerate(selected):
            try:
                essay, notes_href = parse_inline_essay(
                    entry.slug, entry.url, fetch_html(client, entry.url)
                )
                if notes_href:
                    time.sleep(REQUEST_DELAY_S)
                    essay.footnotes = parse_notes_page(fetch_html(client, f"{BASE}/{notes_href}"))
                (essays_dir / f"{entry.slug}.json").write_text(
                    _dump(essay.as_dict()), encoding="utf-8"
                )
                rows.append(essay.index_row())
                stats.written += 1
                stats.words += essay.word_count
                log.info(
                    "scrape.ok",
                    slug=entry.slug,
                    paragraphs=len(essay.paragraphs),
                    footnotes=len(essay.footnotes),
                    words=essay.word_count,
                )
            except Exception as exc:  # one bad page must not abort the catalogue
                stats.skipped.append(entry.slug)
                log.warning("scrape.skip", slug=entry.slug, url=entry.url, error=str(exc))

            if i < len(selected) - 1:
                time.sleep(REQUEST_DELAY_S)

        (data_dir / "index.json").write_text(_dump(rows), encoding="utf-8")
        log.info("scrape.complete", written=stats.written, requested=stats.requested)

    return stats


def _dump(payload: Any) -> str:
    """Match the formatting of the committed corpus (2-space, no trailing newline)."""
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = [
    "BASE",
    "INDEX_URL",
    "Essay",
    "IndexEntry",
    "ScrapeStats",
    "fetch_html",
    "parse_index",
    "parse_inline_essay",
    "parse_notes_page",
    "scrape_catalog",
    "text_with_breaks",
]
