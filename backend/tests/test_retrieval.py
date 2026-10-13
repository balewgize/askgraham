"""Hybrid retrieval: fusion and result shaping.

The database-backed paths are exercised end to end against the live Postgres
elsewhere. What is unit-tested here is the fusion arithmetic and the pure
transformations, because a silent bug in RRF changes every ranking.
"""

import pytest

from core.models import Chunk
from rag.retrieval import (
    SearchHit,
    chunk_signature,
    dedupe_by_essay,
    hybrid_search,
    rrf_fuse,
)


class _FakeEmbedder:
    model_name = "fake/model"


def test_rrf_rewards_appearing_in_both_rankings() -> None:
    # doc 2 is 2nd dense and 1st lexical; doc 1 is 1st dense only.
    fused = rrf_fuse({1: 1, 2: 2}, {2: 1, 3: 2}, k=60)
    assert max(fused, key=lambda d: fused[d]) == 2
    assert fused[2] > fused[1] > fused[3]


def test_rrf_of_a_single_ranking_preserves_rank_order() -> None:
    fused = rrf_fuse({7: 1, 8: 2, 9: 3}, k=60)
    assert fused[7] > fused[8] > fused[9]


def test_rrf_with_no_rankings_is_empty() -> None:
    assert rrf_fuse(k=60) == {}


def test_rrf_k_dampens_high_ranks() -> None:
    """A larger k makes the top rank matter less, as the formula intends."""
    small = rrf_fuse({1: 1}, {2: 1}, k=1)
    large = rrf_fuse({1: 1}, {2: 1}, k=1000)
    assert small[1] > large[1]


def test_rrf_fuses_a_third_title_ranking() -> None:
    """The title arm is a peer of the dense and lexical arms."""
    fused = rrf_fuse({1: 1}, {2: 1}, {3: 1}, k=60)
    assert len(fused) == 3
    assert fused[1] == fused[2] == fused[3]


def test_rrf_lifts_a_document_matched_by_title_and_body() -> None:
    """A title hit plus a body hit must beat a single-arm hit."""
    fused = rrf_fuse({1: 1}, {2: 1}, {2: 1}, k=60)
    assert max(fused, key=lambda d: fused[d]) == 2
    assert fused[2] > fused[1]


def test_rrf_weights_let_a_field_outrank_a_peer() -> None:
    """The title arm carries more than the dense arm — a BM25F-style boost."""
    plain = rrf_fuse({1: 1}, {2: 1}, k=60)
    weighted = rrf_fuse({1: 1}, {2: 1}, k=60, weights=[1.0, 3.0])
    assert plain[1] == plain[2]
    assert weighted[2] > weighted[1]


def test_rrf_rejects_a_weight_per_ranking_mismatch() -> None:
    with pytest.raises(ValueError):
        rrf_fuse({1: 1}, {2: 1}, k=60, weights=[1.0])


def _hit(slug: str, score: float) -> SearchHit:
    return SearchHit(
        slug=slug,
        title=slug.title(),
        date=None,
        reading_time_min=1,
        text="x",
        score=score,
        start_paragraph=0,
        end_paragraph=0,
    )


def test_dedupe_by_essay_keeps_the_best_ranked_chunk() -> None:
    hits = [_hit("a", 0.9), _hit("b", 0.8), _hit("a", 0.7), _hit("c", 0.6)]
    out = dedupe_by_essay(hits)
    assert [h.slug for h in out] == ["a", "b", "c"]
    assert out[0].score == 0.9


def test_chunk_signature_names_model_and_parameters() -> None:
    signature = chunk_signature(_FakeEmbedder())  # type: ignore[arg-type]
    assert "model=fake/model" in signature
    assert "max_tokens=" in signature
    assert "overlap=" in signature


async def test_blank_query_short_circuits_without_a_session() -> None:
    """An empty query must not touch the database or load a model."""
    result = await hybrid_search(None, "   ")  # type: ignore[arg-type]
    assert result.hits == []
    assert result.elapsed_ms == 0.0


def test_chunk_model_has_a_generated_tsvector_excluding_python_updates() -> None:
    """The tsvector is computed by Postgres, so Python can never forget it."""
    column = Chunk.__table__.c.tsv
    assert column.computed is not None
    assert column.computed.persisted
