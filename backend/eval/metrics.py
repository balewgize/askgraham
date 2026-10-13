"""Ranking metrics: recall@k, MRR and nDCG@k.

Pure functions over a *ranked list of relevance gains*. A gain is the relevance
of the item at that rank: `1.0` for a hit, `0.0` for a miss, or a larger number
for graded relevance. Nothing here touches the database, the model, or a
`SearchHit` — the runner is the layer that turns chunks into gains. That split is
what makes a silent ranking change impossible to hide: the arithmetic is tested
in isolation, and the runner is a thin, readable mapping on top.

Two conventions are worth stating because they are easy to get wrong:

**Recall is capped at `n_relevant`.** A query with one gold item can retrieve it
once, not once per returned chunk. The cap makes `recall@k` mean "how much of the
relevant set did we get", which for a single gold essay is the standard
success@k: 1 if the essay is in the top `k`, else 0.

**nDCG normalizes against an explicit ideal.** The ideal ranking of the whole
relevant set is not knowable from the retrieved head alone, so the caller passes
`ideal_gains`. Leaving it implicit (sorting the retrieved gains) silently
understates the denominator whenever the retriever is wrong.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass


def recall_at_k(gains: Sequence[float], k: int, n_relevant: int) -> float:
    """Fraction of the relevant set found in the top `k`.

    Gains are treated as binary for recall (any positive gain is a hit), because
    recall is about coverage, not order. `n_relevant` is how many relevant items
    exist in total; without it there is no denominator and the number would be a
    precision dressed up as a recall.
    """
    if n_relevant <= 0:
        raise ValueError("n_relevant must be positive")
    if k <= 0:
        return 0.0
    found = sum(1 for gain in gains[:k] if gain > 0)
    return min(found, n_relevant) / n_relevant


def reciprocal_rank(gains: Sequence[float]) -> float:
    """1 / rank of the first relevant item, or 0 if none were retrieved."""
    for rank, gain in enumerate(gains, start=1):
        if gain > 0:
            return 1.0 / rank
    return 0.0


def dcg_at_k(gains: Sequence[float], k: int) -> float:
    """Discounted cumulative gain over the top `k`, log base 2 with rank 1 first."""
    return sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains[:k], start=1))


def ndcg_at_k(gains: Sequence[float], k: int, ideal_gains: Sequence[float]) -> float:
    """DCG@k divided by the best achievable DCG@k for this query.

    `ideal_gains` describes the ideal ordering of the complete relevant set. For
    a single gold item that is `[1.0]`, which makes nDCG@k the discounted gain of
    wherever the item was found.
    """
    ideal = dcg_at_k(ideal_gains, k)
    if ideal <= 0:
        return 0.0
    return dcg_at_k(gains, k) / ideal


def paragraph_coverage(
    hit_ranges: Sequence[tuple[int, int]],
    gold_paragraphs: Sequence[int],
    k: int,
) -> float:
    """Fraction of gold paragraphs touched by at least one top-`k` chunk.

    This is what the hand-authored paragraph refs are for. It is stricter than
    the essay-level metrics: a chunk that is merely somewhere in the right essay
    does not count unless it actually covers a paragraph the answer lives in.
    """
    if not gold_paragraphs:
        return 1.0
    wanted = set(gold_paragraphs)
    covered: set[int] = set()
    for start, end in hit_ranges[:k]:
        for position in wanted:
            if start <= position <= end:
                covered.add(position)
    return len(covered) / len(wanted)


@dataclass(frozen=True)
class RankingMetrics:
    """One query's retrieval scores, averaged with its peers for the report."""

    recall: float
    mrr: float
    ndcg: float

    def as_dict(self) -> dict[str, float]:
        return {"recall": self.recall, "mrr": self.mrr, "ndcg": self.ndcg}


def evaluate_ranking(
    gains: Sequence[float],
    *,
    k: int,
    n_relevant: int,
    ideal_gains: Sequence[float],
) -> RankingMetrics:
    """All three ranking metrics for one query, so the runner maps once."""
    return RankingMetrics(
        recall=recall_at_k(gains, k, n_relevant),
        mrr=reciprocal_rank(gains),
        ndcg=ndcg_at_k(gains, k, ideal_gains),
    )


def mean_rankings(rows: Sequence[RankingMetrics]) -> RankingMetrics:
    """Element-wise mean. An empty sequence scores zero rather than NaN."""
    if not rows:
        return RankingMetrics(recall=0.0, mrr=0.0, ndcg=0.0)
    count = len(rows)
    return RankingMetrics(
        recall=sum(row.recall for row in rows) / count,
        mrr=sum(row.mrr for row in rows) / count,
        ndcg=sum(row.ndcg for row in rows) / count,
    )


__all__ = [
    "RankingMetrics",
    "dcg_at_k",
    "evaluate_ranking",
    "mean_rankings",
    "ndcg_at_k",
    "paragraph_coverage",
    "recall_at_k",
    "reciprocal_rank",
]
