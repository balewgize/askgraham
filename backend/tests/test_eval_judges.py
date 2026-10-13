"""Answer measurement: grounding, citations and the LLM judges.

The deterministic half is tested directly. The judge half is tested through a
mock transport, so the schema validation and the score clamping are pinned
without a network call.
"""

import json
from typing import Any

import httpx
import pytest

from eval.judges import (
    AnswerJudgement,
    AnswerMetrics,
    CitationValidity,
    JudgeScore,
    QuoteGrounding,
    aggregate_judgements,
    check_citations,
    extract_quotes,
    ground_quotes,
    judge_answer,
    judge_faithfulness,
    judge_relevance,
    normalize_text,
    parse_citations,
)
from llm.client import OpenRouterClient
from llm.generation import Source


def _source(
    slug: str = "ds", start: int = 0, end: int = 4, text: str = "Make something people want."
) -> Source:
    return Source(
        slug=slug,
        title="Do Things that Don't Scale",
        start_paragraph=start,
        end_paragraph=end,
        text=text,
    )


# ── normalize_text ────────────────────────────────────────────────────


def test_normalize_folds_typography_and_case() -> None:
    assert normalize_text("Don\u2019t \u2014 stop") == "don't - stop"


def test_normalize_collapses_whitespace() -> None:
    assert normalize_text("  a \n\n b\tc ") == "a b c"


def test_normalize_folds_curly_double_quotes() -> None:
    assert normalize_text("\u201cquoted\u201d") == '"quoted"'


def test_normalize_of_empty_is_empty() -> None:
    assert normalize_text("") == ""


# ── quotes ────────────────────────────────────────────────────────────


def test_extract_quotes_finds_straight_and_curly() -> None:
    answer = 'He says "make something people want" and \u201cdo things that don\u2019t scale\u201d.'
    quotes = extract_quotes(answer)
    assert quotes == ["make something people want", "do things that don\u2019t scale"]


def test_extract_quotes_drops_short_emphasis() -> None:
    assert extract_quotes('the "best" way') == []


def test_extract_quotes_deduplicates_in_order() -> None:
    answer = '"make something people want" ... "make something people want" ... "talk to users"'
    assert extract_quotes(answer) == ["make something people want", "talk to users"]


def test_extract_quotes_of_a_plain_answer_is_empty() -> None:
    assert extract_quotes("No quotes here at all.") == []


def test_ground_quotes_matches_verbatim_text() -> None:
    result = ground_quotes('He said "make something people want" here.', [_source()])
    assert result.total == 1
    assert result.grounded == 1
    assert result.rate == 1.0


def test_ground_quotes_matches_across_typography() -> None:
    source = _source(text="You don\u2019t need a big idea.")
    result = ground_quotes('He said "You don\'t need a big idea" plainly.', [source])
    assert result.grounded == 1


def test_ground_quotes_flags_an_invented_quote() -> None:
    result = ground_quotes('He said "raise money only from customers".', [_source()])
    assert result.total == 1
    assert result.grounded == 0
    assert result.rate == 0.0
    assert result.ungrounded == ("raise money only from customers",)


def test_ground_quotes_without_quotes_scores_zero() -> None:
    """An unquoted answer is not evidence of grounding."""
    result = ground_quotes("A plausible answer with no quotes.", [_source()])
    assert result.total == 0
    assert result.rate == 0.0


def test_ground_quotes_checks_all_sources_not_only_the_first() -> None:
    sources = [_source(text="first passage"), _source(slug="top", text="the top idea in your mind")]
    result = ground_quotes('"the top idea in your mind"', sources)
    assert result.grounded == 1


def test_ground_quotes_ignores_a_citation_token_inside_the_quote() -> None:
    """The model cites inline; a token inside the quotes is protocol, not text."""
    result = ground_quotes('He said "make something people want [ds#0-4]".', [_source()])
    assert result.grounded == 1


def test_ground_quotes_ignores_boundary_punctuation() -> None:
    source = _source(text="the most successful startups almost all begin as")
    result = ground_quotes(
        'He says \u2014 "the most successful startups almost all begin as."', [source]
    )
    assert result.grounded == 1


def test_ground_quotes_allows_an_elision_when_both_sides_are_verbatim() -> None:
    source = _source(text="do things that don't scale because the founders make them take off")
    result = ground_quotes(
        'He says "do things that don\'t scale ... founders make them take off".', [source]
    )
    assert result.grounded == 1


def test_ground_quotes_rejects_an_elision_with_an_invented_side() -> None:
    source = _source(text="do things that don't scale")
    result = ground_quotes('"do things that don\'t scale ... invent a new market"', [source])
    assert result.grounded == 0
    assert result.ungrounded == ("do things that don't scale ... invent a new market",)


# ── citations ─────────────────────────────────────────────────────────


def test_parse_citations_extracts_tokens() -> None:
    answer = "Claim [ds#0-4] and another [95#2-3]."
    citations = parse_citations(answer)
    assert [c.token for c in citations] == ["ds#0-4", "95#2-3"]


def test_parse_citations_deduplicates() -> None:
    assert len(parse_citations("[ds#0-4] then again [ds#0-4]")) == 1


def test_parse_citations_of_a_plain_answer_is_empty() -> None:
    assert parse_citations("No citations here.") == []


def test_check_citations_accepts_exact_tokens() -> None:
    validity = check_citations("See [ds#0-4].", [_source()])
    assert validity.total == 1
    assert validity.valid == 1
    assert validity.precision == 1.0


def test_check_citations_rejects_a_near_miss_range() -> None:
    """`ds#0-3` and `ds#0-4` are different claims; a near miss is invented."""
    validity = check_citations("See [ds#0-3].", [_source(end=4)])
    assert validity.valid == 0
    assert validity.invalid == ("ds#0-3",)


def test_check_citations_rejects_an_unknown_slug() -> None:
    validity = check_citations("See [unknown#0-1].", [_source()])
    assert validity.precision == 0.0


def test_check_citations_without_citations_precision_is_zero() -> None:
    assert check_citations("No citations.", [_source()]).precision == 0.0


# ── LLM judges (mock transport) ───────────────────────────────────────


def _client(**overrides: Any) -> OpenRouterClient:
    return OpenRouterClient(
        api_key="test-key",
        base_url="https://example.test",
        **overrides,
    )


def _judge_response(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        request=httpx.Request("POST", "https://example.test"),
    )


async def test_judge_faithfulness_parses_and_clamps_the_score() -> None:
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return _judge_response(
            {"score": 9, "supported": True, "unsupported_claims": [], "reason": " grounded "}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        score = await judge_faithfulness(
            question="q",
            answer="a",
            sources=[_source()],
            client=_client(),
            http=http,
            temperature=0.0,
            seed=7,
        )
    assert score.score == 5
    assert score.verdict is True
    assert score.reason == "grounded"
    assert score.normalized == 1.0
    assert sent["temperature"] == 0.0
    assert sent["seed"] == 7
    assert sent["response_format"]["json_schema"]["strict"] is True


async def test_judge_scores_are_normalized_to_zero_one() -> None:
    assert JudgeScore(1, False, "").normalized == 0.0
    assert JudgeScore(3, False, "").normalized == 0.5
    assert JudgeScore(5, True, "").normalized == 1.0


async def test_judge_relevance_reports_issues() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _judge_response({"score": 2, "answered": False, "reason": "off topic"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        score = await judge_relevance(
            question="q", answer="a", client=_client(), http=http, temperature=0.0, seed=1
        )
    assert score.score == 2
    assert score.verdict is False


async def test_judge_answer_records_a_provider_failure_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        judgement = await judge_answer(
            case_id="c1",
            question="q",
            answer='He said "make something people want". Cite [ds#0-4].',
            sources=[_source()],
            client=_client(max_attempts=1),
            http=http,
            temperature=0.0,
            seed=1,
        )
    assert judgement.error is not None
    assert judgement.faithfulness.score == 0
    # The deterministic checks still ran, which is the point of the split.
    assert judgement.grounding.grounded == 1
    assert judgement.citation_validity.valid == 1


# ── aggregation ───────────────────────────────────────────────────────


def _judgement(
    case_id: str,
    *,
    faithfulness: int = 5,
    relevance: int = 5,
    citation: int = 5,
    grounded: int = 1,
    quotes: int = 1,
    valid: int = 1,
    citations: int = 1,
    error: str | None = None,
) -> AnswerJudgement:
    return AnswerJudgement(
        case_id=case_id,
        question="q",
        answer="a",
        faithfulness=JudgeScore(faithfulness, True, ""),
        relevance=JudgeScore(relevance, True, ""),
        citation_correctness=JudgeScore(citation, True, ""),
        grounding=QuoteGrounding(total=quotes, grounded=grounded),
        citation_validity=CitationValidity(total=citations, valid=valid),
        error=error,
    )


def test_aggregate_judgements_averages_normalized_scores() -> None:
    metrics = aggregate_judgements(
        [_judgement("a", faithfulness=5), _judgement("b", faithfulness=3)]
    )
    assert isinstance(metrics, AnswerMetrics)
    assert metrics.count == 2
    assert metrics.faithfulness == pytest.approx(0.75)


def test_aggregate_judgements_excludes_failed_scores_from_the_means() -> None:
    metrics = aggregate_judgements(
        [_judgement("a", faithfulness=5), _judgement("b", faithfulness=0, error="timeout")]
    )
    assert metrics.count == 2
    assert metrics.failures == 1
    assert metrics.faithfulness == 1.0


def test_aggregate_judgements_counts_quotes_and_citations() -> None:
    metrics = aggregate_judgements([_judgement("a", quotes=2, grounded=1, citations=2, valid=2)])
    assert metrics.quotes == 2
    assert metrics.grounded_quotes == 1
    assert metrics.citations == 2
    assert metrics.quote_grounding == 0.5
    assert metrics.citation_precision == 1.0


def test_aggregate_grounding_is_micro_averaged() -> None:
    """An answer with no quotes must not count as an ungrounded one."""
    metrics = aggregate_judgements(
        [
            _judgement("a", quotes=0, grounded=0),
            _judgement("b", quotes=4, grounded=3),
        ]
    )
    assert metrics.quotes == 4
    assert metrics.grounded_quotes == 3
    assert metrics.quote_grounding == 0.75


def test_aggregate_of_only_failures_is_a_clean_zero_run() -> None:
    metrics = aggregate_judgements(
        [_judgement("a", faithfulness=0, relevance=0, citation=0, error="boom")]
    )
    assert metrics.count == 1
    assert metrics.failures == 1
    assert metrics.faithfulness == 0.0
