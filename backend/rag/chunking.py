"""Paragraph-aware, token-budgeted chunking.

A chunk is a contiguous run of paragraphs, small enough to embed whole and
large enough to mean something on its own. Two properties are deliberate:

**Paragraph boundaries are respected where possible.** A chunk that ends
mid-sentence retrieves worse and cites worse. Whole paragraphs are packed until
the next one would blow the budget; only a paragraph that is itself larger than
the budget is split, and then at sentence boundaries first.

**Every chunk remembers which paragraphs it came from.** `start_paragraph` and
`end_paragraph` are the citation. A citation that cannot be resolved back to a
source paragraph is not a citation, which is why the range is carried through
rather than reconstructed later from the text.

The token budget is enforced with an injected `count_tokens`, so the chunker is
pure and testable without loading a model. `index_chunks` injects the embedding
model's own tokenizer; the default here is a conservative whitespace estimate.
`max_tokens` is set below the model's truncation limit (384 vs 512) so that
sub-word merges at join boundaries cannot silently truncate a chunk.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from config import settings

CountTokens = Callable[[str], int]

# A "word" for the fallback counter. Sentence splitting keeps the terminator on
# the left piece, so `"a. B"` -> `["a.", "B"]`.
_WORD_RE = re.compile(r"\S+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def approximate_token_count(text: str) -> int:
    """Whitespace-word count.

    Conservative for English: a BPE tokenizer usually produces *more* tokens
    than words, so budgeting in words leaves headroom under the model limit.
    Accurate enough for tests, and replaced by the real tokenizer at index time.
    """
    return len(_WORD_RE.findall(text))


@dataclass(frozen=True)
class Chunk:
    """One retrieval unit, ready to embed and store."""

    slug: str
    position: int
    start_paragraph: int
    end_paragraph: int
    text: str
    token_count: int


@dataclass(frozen=True)
class _Unit:
    """A piece of one paragraph. A whole paragraph, unless it was too big."""

    paragraph: int
    text: str
    tokens: int


def _split_by_words(text: str, *, max_tokens: int, count_tokens: CountTokens) -> list[str]:
    """Last resort for a single sentence that exceeds the budget on its own."""
    pieces: list[str] = []
    current: list[str] = []
    tokens = 0
    for word in text.split():
        cost = count_tokens(word)
        if current and tokens + cost > max_tokens:
            pieces.append(" ".join(current))
            current = []
            tokens = 0
        current.append(word)
        tokens += cost
    if current:
        pieces.append(" ".join(current))
    return pieces


def _split_oversized(text: str, *, max_tokens: int, count_tokens: CountTokens) -> list[str]:
    """Split a too-large paragraph at sentence boundaries, then words if needed."""
    pieces: list[str] = []
    current: list[str] = []
    tokens = 0
    for sentence in _SENTENCE_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        cost = count_tokens(sentence)
        if cost > max_tokens:
            if current:
                pieces.append(" ".join(current))
                current, tokens = [], 0
            pieces.extend(
                _split_by_words(sentence, max_tokens=max_tokens, count_tokens=count_tokens)
            )
            continue
        if current and tokens + cost > max_tokens:
            pieces.append(" ".join(current))
            current, tokens = [], 0
        current.append(sentence)
        tokens += cost
    if current:
        pieces.append(" ".join(current))
    return pieces


def _units(paragraphs: list[str], *, max_tokens: int, count_tokens: CountTokens) -> list[_Unit]:
    out: list[_Unit] = []
    for index, raw in enumerate(paragraphs):
        text = raw.strip()
        if not text:
            continue
        cost = count_tokens(text)
        if cost <= max_tokens:
            out.append(_Unit(index, text, cost))
            continue
        for piece in _split_oversized(text, max_tokens=max_tokens, count_tokens=count_tokens):
            out.append(_Unit(index, piece, count_tokens(piece)))
    return out


def _overlap_start(units: list[_Unit], start: int, end: int, overlap_tokens: int) -> int:
    """First unit index of the next chunk, walking back for overlap.

    Never returns `start` or less: the next chunk must include at least one unit
    the current one did not, or the loop cannot terminate.
    """
    back = end
    acc = 0
    while back > start and acc + units[back - 1].tokens <= overlap_tokens:
        back -= 1
        acc += units[back].tokens
    if back <= start:
        back = start + 1
    return back


def chunk_paragraphs(
    slug: str,
    paragraphs: list[str],
    *,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
    count_tokens: CountTokens = approximate_token_count,
) -> list[Chunk]:
    """Group `paragraphs` into overlapping, token-budgeted chunks.

    Empty paragraphs are dropped; `position` counts only emitted chunks, so it
    stays contiguous. `start_paragraph`/`end_paragraph` are indices into the
    original list, so a citation survives the empty-paragraph drop.
    """
    budget = max_tokens if max_tokens is not None else settings.chunk_max_tokens
    overlap = overlap_tokens if overlap_tokens is not None else settings.chunk_overlap_tokens
    if budget <= 0:
        raise ValueError("max_tokens must be positive")
    overlap = max(0, min(overlap, budget - 1))

    units = _units(paragraphs, max_tokens=budget, count_tokens=count_tokens)
    chunks: list[Chunk] = []
    start = 0
    while start < len(units):
        end = start
        tokens = 0
        while end < len(units) and tokens + units[end].tokens <= budget:
            tokens += units[end].tokens
            end += 1

        if end == start:
            # A lone unit still over budget: `_split_oversized` should have
            # prevented this, but emitting it beats dropping content.
            end = start + 1
            tokens = units[start].tokens

        chunks.append(
            Chunk(
                slug=slug,
                position=len(chunks),
                start_paragraph=units[start].paragraph,
                end_paragraph=units[end - 1].paragraph,
                text="\n\n".join(unit.text for unit in units[start:end]),
                token_count=tokens,
            )
        )

        if end >= len(units):
            break
        start = _overlap_start(units, start, end, overlap)

    return chunks


__all__ = ["Chunk", "approximate_token_count", "chunk_paragraphs"]
