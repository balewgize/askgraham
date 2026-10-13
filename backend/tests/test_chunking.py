"""Chunker behaviour.

The chunker is pure, so these run with a word-count "tokenizer" and stay fast
and deterministic. What is being protected is that no text is lost, that every
chunk can be traced back to source paragraphs, and that the budget is honoured.
"""

import pytest

from rag.chunking import Chunk, approximate_token_count, chunk_paragraphs

WORDS = lambda text: len(text.split())  # noqa: E731 - a test double, not a function


def _words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def test_approximate_token_count_counts_words() -> None:
    assert approximate_token_count("one two three") == 3
    assert approximate_token_count("   ") == 0


def test_empty_essay_produces_no_chunks() -> None:
    assert chunk_paragraphs("x", [], count_tokens=WORDS) == []
    assert chunk_paragraphs("x", ["", "   "], count_tokens=WORDS) == []


def test_single_short_paragraph_is_one_chunk() -> None:
    chunks = chunk_paragraphs("x", ["hello world"], max_tokens=100, count_tokens=WORDS)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk == Chunk("x", 0, 0, 0, "hello world", 2)


def test_positions_are_contiguous_from_zero() -> None:
    paragraphs = [_words(10) for _ in range(6)]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=25, overlap_tokens=0, count_tokens=WORDS)
    assert [c.position for c in chunks] == list(range(len(chunks)))
    assert len(chunks) > 1


def test_chunks_stay_within_the_token_budget() -> None:
    paragraphs = [_words(5) for _ in range(10)]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=12, overlap_tokens=0, count_tokens=WORDS)
    # The packer never exceeds the budget, and never emits an empty chunk.
    assert all(0 < c.token_count <= 12 for c in chunks)


def test_paragraph_indices_point_at_the_source() -> None:
    paragraphs = [_words(6) for _ in range(4)]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=10, overlap_tokens=0, count_tokens=WORDS)
    for chunk in chunks:
        assert 0 <= chunk.start_paragraph <= chunk.end_paragraph < len(paragraphs)


def test_empty_paragraphs_are_dropped_but_indices_are_preserved() -> None:
    """A citation index must survive blank paragraphs being skipped."""
    paragraphs = ["", "alpha", "", "", "beta"]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=100, count_tokens=WORDS)
    assert len(chunks) == 1
    assert chunks[0].text == "alpha\n\nbeta"
    assert chunks[0].start_paragraph == 1
    assert chunks[0].end_paragraph == 4


def test_overlap_repeats_the_tail_of_the_previous_chunk() -> None:
    paragraphs = [_words(2) for _ in range(6)]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=5, overlap_tokens=2, count_tokens=WORDS)
    assert len(chunks) >= 2
    # The last paragraph of chunk n appears at the start of chunk n+1.
    tail = chunks[0].text.split("\n\n")[-1]
    assert chunks[1].text.startswith(tail)


def test_zero_overlap_does_not_repeat_content() -> None:
    paragraphs = [f"p{i} {_words(3)}" for i in range(4)]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=8, overlap_tokens=0, count_tokens=WORDS)
    joined = "\n\n".join(c.text for c in chunks).split("\n\n")
    # Every paragraph appears exactly once when there is no overlap.
    assert joined == paragraphs


def test_oversized_paragraph_is_split_not_truncated() -> None:
    paragraphs = [_words(50)]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=10, overlap_tokens=0, count_tokens=WORDS)
    assert len(chunks) > 1
    assert all(c.start_paragraph == 0 and c.end_paragraph == 0 for c in chunks)
    words = " ".join(c.text for c in chunks).split()
    assert len(words) == 50, "words were lost splitting an oversized paragraph"


def test_oversized_single_sentence_falls_back_to_words() -> None:
    """A sentence longer than the budget has no boundary to split on."""
    paragraphs = [" ".join(["x"] * 30)]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=8, count_tokens=WORDS)
    assert all(c.token_count <= 8 for c in chunks)
    assert len(" ".join(c.text for c in chunks).split()) == 30


def test_large_overlap_still_terminates_and_keeps_all_text() -> None:
    """Overlap is clamped to budget-1 so the loop cannot stall or lose text."""
    paragraphs = [_words(3) for _ in range(5)]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=4, overlap_tokens=99, count_tokens=WORDS)
    assert len(chunks) >= 5
    assert all(c.token_count <= 4 for c in chunks)


def test_budget_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        chunk_paragraphs("x", ["a"], max_tokens=0, count_tokens=WORDS)


def test_sentences_split_before_words_when_possible() -> None:
    """An oversized paragraph splits at sentence boundaries, not mid-sentence."""
    paragraphs = ["Alpha one. Beta two. Gamma three."]
    chunks = chunk_paragraphs("x", paragraphs, max_tokens=4, overlap_tokens=0, count_tokens=WORDS)
    assert [c.text for c in chunks] == ["Alpha one. Beta two.", "Gamma three."]
