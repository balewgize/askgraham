"""Retrieval metrics.

The whole point of the eval is that a ranking change is provable, so the metric
arithmetic is pinned here against hand-computed values. A silent bug in nDCG
would quietly flatter every future tuning run.
"""

import math

import pytest

from eval.metrics import (
    RankingMetrics,
    dcg_at_k,
    evaluate_ranking,
    mean_rankings,
    ndcg_at_k,
    paragraph_coverage,
    recall_at_k,
    reciprocal_rank,
)


def test_recall_counts_hits_in_the_top_k() -> None:
    gains = [1.0, 0.0, 1.0, 0.0]
    assert recall_at_k(gains, 1, n_relevant=2) == 0.5
    assert recall_at_k(gains, 2, n_relevant=2) == 0.5
    assert recall_at_k(gains, 3, n_relevant=2) == 1.0


def test_recall_is_capped_at_the_relevant_set() -> None:
    """One gold item retrieved once is full recall, not 200%."""
    assert recall_at_k([1.0, 1.0, 1.0], 3, n_relevant=1) == 1.0


def test_recall_misses_score_zero() -> None:
    assert recall_at_k([0.0, 0.0], 2, n_relevant=1) == 0.0


def test_recall_with_zero_k_is_zero() -> None:
    assert recall_at_k([1.0], 0, n_relevant=1) == 0.0


def test_recall_requires_a_positive_relevant_count() -> None:
    with pytest.raises(ValueError, match="n_relevant"):
        recall_at_k([1.0], 3, n_relevant=0)


def test_reciprocal_rank_uses_the_first_relevant_rank() -> None:
    assert reciprocal_rank([0.0, 0.0, 1.0, 1.0]) == pytest.approx(1 / 3)


def test_reciprocal_rank_without_a_hit_is_zero() -> None:
    assert reciprocal_rank([0.0, 0.0]) == 0.0


def test_dcg_discounts_known_ranks() -> None:
    # 1/log2(2) + 0 + 1/log2(4) = 1 + 0 + 0.5
    assert dcg_at_k([1.0, 0.0, 1.0], 3) == pytest.approx(1.5)


def test_dcg_respects_k() -> None:
    assert dcg_at_k([1.0, 1.0], 1) == pytest.approx(1.0)


def test_ndcg_normalizes_against_the_ideal() -> None:
    # Retrieved: only rank 0. Ideal: two relevant items at ranks 0 and 1.
    ideal = 1.0 + 1.0 / math.log2(3)
    assert ndcg_at_k([1.0], 2, [1.0, 1.0]) == pytest.approx(1.0 / ideal)


def test_ndcg_of_a_perfect_single_gold_ranking_is_one() -> None:
    assert ndcg_at_k([1.0], 10, [1.0]) == pytest.approx(1.0)


def test_ndcg_of_a_deep_hit_is_discounted() -> None:
    assert ndcg_at_k([0.0, 0.0, 1.0], 10, [1.0]) == pytest.approx(1 / math.log2(4))


def test_ndcg_with_no_ideal_is_zero() -> None:
    assert ndcg_at_k([1.0], 10, []) == 0.0


def test_evaluate_ranking_composes_all_three() -> None:
    metrics = evaluate_ranking([0.0, 1.0], k=5, n_relevant=1, ideal_gains=[1.0])
    assert metrics.recall == 1.0
    assert metrics.mrr == pytest.approx(0.5)
    assert metrics.ndcg == pytest.approx(1 / math.log2(3))


def test_mean_rankings_averages_elementwise() -> None:
    rows = [
        RankingMetrics(recall=1.0, mrr=1.0, ndcg=1.0),
        RankingMetrics(recall=0.0, mrr=0.5, ndcg=0.25),
    ]
    mean = mean_rankings(rows)
    assert mean.recall == 0.5
    assert mean.mrr == 0.75
    assert mean.ndcg == 0.625


def test_mean_rankings_of_nothing_is_zero_not_nan() -> None:
    assert mean_rankings([]) == RankingMetrics(recall=0.0, mrr=0.0, ndcg=0.0)


def test_paragraph_coverage_counts_only_overlapping_chunks() -> None:
    # Chunks cover paragraphs 0-1 and 3-3; gold is {1, 2, 3}.
    coverage = paragraph_coverage([(0, 1), (3, 3)], [1, 2, 3], k=2)
    assert coverage == pytest.approx(2 / 3)


def test_paragraph_coverage_respects_k() -> None:
    assert paragraph_coverage([(0, 1), (2, 2)], [0, 2], k=1) == pytest.approx(0.5)


def test_paragraph_coverage_of_a_full_hit_is_one() -> None:
    assert paragraph_coverage([(2, 4)], [3, 4], k=10) == 1.0


def test_paragraph_coverage_with_no_overlap_is_zero() -> None:
    assert paragraph_coverage([(5, 6)], [1, 2], k=10) == 0.0


def test_paragraph_coverage_with_no_gold_is_vacuous() -> None:
    assert paragraph_coverage([(0, 1)], [], k=10) == 1.0


def test_paragraph_coverage_with_zero_k_is_zero() -> None:
    assert paragraph_coverage([(0, 9)], [1], k=0) == 0.0
