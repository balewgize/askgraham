"""Answer-quality measurement: LLM-as-judge plus deterministic grounding.

Retrieval metrics say whether the right passage was found. They say nothing
about the answer built from it. This module measures the answer in two layers,
picked so that the cheap layer catches the failure the expensive one cannot be
trusted on:

1. **Deterministic checks** — quote grounding and citation validity. A quoted
   span either appears in the retrieved sources or it does not, and a citation
   token either names a real source or it does not. No model, no cost, no room
   for a judge to be talked into a hallucination it likes. This is the check that
   answers "how do you know the model isn't inventing quotes?".
2. **LLM-as-judge** — faithfulness, relevance and citation correctness. These
   need judgment, so they use `chat_json` at temperature 0 with a fixed seed, and
   return a 1-5 score with the specific claims or citations they doubted.

The two are deliberately both present. A judge can be wrong; a substring match
cannot. Where they disagree is itself the finding.
"""

import asyncio
import re
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from config import settings
from core.logging_config import log
from llm.client import InvalidResponseError, OpenRouterClient, collapse_whitespace
from llm.generation import Source, build_context

# Cheap model-facing labels. The tokens are the same ones the answer was told to
# cite, so the judge reasons over the exact strings the generator saw.
JUDGE_SCORE_MIN = 1
JUDGE_SCORE_MAX = 5

# A quoted span, in either straight or typographic double quotes. The 8-char
# floor drops throwaway emphasis ("the 'best' way") while keeping short real
# quotes ("do things", "make something people want").
_QUOTE_RE = re.compile(r"[“\"]([^“”\"]{8,})[”\"]")

# The citation token `[slug#start-end]`. Slugs are lowercase alphanumerics and
# hyphens — the corpus has numeric slugs too ("95", "13sentences").
_CITATION_RE = re.compile(r"\[([a-z0-9][a-z0-9-]*)#(\d+)-(\d+)\]")

# Typography the corpus and the model disagree on, normalized to one form so a
# quote matches on its words rather than on which quote glyph was emitted.
# Written as escapes because the literal glyphs are "ambiguous unicode" (RUF001)
# and reading them here is harder than reading the codepoint.
_TRANSLATIONS = str.maketrans(
    {
        "\u201c": '"',  # left double quotation mark
        "\u201d": '"',  # right double quotation mark
        "\u2018": "'",  # left single quotation mark
        "\u2019": "'",  # right single quotation mark / apostrophe
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2026": "...",  # horizontal ellipsis
        "\u00a0": " ",  # non-breaking space
    }
)


def normalize_text(value: str) -> str:
    """Fold typography, whitespace and case for tolerant substring matching.

    Tolerant on purpose: the model may re-typeset a quote (curly for straight, an
    em dash for a hyphen) without changing it. It stays strict on content — every
    word and its order must survive — so a reworded quote still fails.
    """
    if not value:
        return ""
    folded = unicodedata.normalize("NFKC", value).translate(_TRANSLATIONS)
    return collapse_whitespace(folded).casefold()


def extract_quotes(answer: str) -> list[str]:
    """Quoted spans in an answer, in order and de-duplicated."""
    quotes: list[str] = []
    for match in _QUOTE_RE.finditer(answer):
        quote = collapse_whitespace(match.group(1))
        if quote and quote not in quotes:
            quotes.append(quote)
    return quotes


@dataclass(frozen=True)
class QuoteGrounding:
    """How many of an answer's quoted spans appear verbatim in the sources."""

    total: int
    grounded: int
    ungrounded: tuple[str, ...] = ()

    @property
    def rate(self) -> float:
        """Grounded fraction. No quotes scores 0 — an unquoted answer is not proof."""
        return self.grounded / self.total if self.total else 0.0


def ground_quotes(answer: str, sources: Sequence[Source]) -> QuoteGrounding:
    """Check every quote in the answer against the concatenated source text.

    A quote is grounded when each of its *fragments* appears verbatim. Fragments
    are what remains after the two things that are formatting rather than
    content:

    - **Citation tokens** inside the quote. The model is told to cite inline and
      sometimes places `[ds#0-4]` inside the quotation marks; that is the app's
      protocol, not an invention.
    - **Elisions** (`...`). A quote that elides the middle is legitimate as long
      as each side is exact.

    Checked against *all* provided sources, not only the cited one: a quote that
    exists somewhere in context is not a hallucination, even if the citation next
    to it is wrong. Citation correctness is a separate metric, judged separately.
    """
    quotes = extract_quotes(answer)
    if not quotes:
        return QuoteGrounding(total=0, grounded=0)
    haystack = normalize_text(" ".join(source.text for source in sources))
    grounded = 0
    ungrounded: list[str] = []
    for quote in quotes:
        fragments = _quote_fragments(quote)
        if fragments and all(normalize_text(fragment) in haystack for fragment in fragments):
            grounded += 1
        else:
            ungrounded.append(quote)
    return QuoteGrounding(total=len(quotes), grounded=grounded, ungrounded=tuple(ungrounded))


# An elision the model may use to skip words inside a quotation.
_ELLIPSIS_RE = re.compile(r"\.\.\.|\u2026")
# Punctuation a verbatim fragment may carry at its edges but the source does not.
# Typographic characters are escapes so they cannot be confused with ASCII (RUF001).
_FRAGMENT_TRIM = (
    " \t\r\n\"'"
    "\u201c\u201d\u2018\u2019"  # curly single/double quotes
    ".,;:!?"
    "\u2013\u2014-"  # en dash, em dash, hyphen
    "()[]"
)


def _quote_fragments(quote: str) -> list[str]:
    """Split a quote into the spans that must each appear verbatim."""
    cleaned = _CITATION_RE.sub(" ", quote)
    fragments: list[str] = []
    for part in _ELLIPSIS_RE.split(cleaned):
        fragment = collapse_whitespace(part).strip(_FRAGMENT_TRIM)
        if len(fragment) > 2:
            fragments.append(fragment)
    return fragments


@dataclass(frozen=True)
class Citation:
    slug: str
    start_paragraph: int
    end_paragraph: int

    @property
    def token(self) -> str:
        return f"{self.slug}#{self.start_paragraph}-{self.end_paragraph}"


def parse_citations(answer: str) -> list[Citation]:
    """Every citation token in the answer, in order and de-duplicated."""
    seen: set[str] = set()
    out: list[Citation] = []
    for match in _CITATION_RE.finditer(answer):
        token = match.group(0)[1:-1]
        if token in seen:
            continue
        seen.add(token)
        out.append(
            Citation(
                slug=match.group(1),
                start_paragraph=int(match.group(2)),
                end_paragraph=int(match.group(3)),
            )
        )
    return out


@dataclass(frozen=True)
class CitationValidity:
    """How many citation tokens point at a source that was actually provided."""

    total: int
    valid: int
    invalid: tuple[str, ...] = ()

    @property
    def precision(self) -> float:
        """Valid fraction. No citations scores 0 — an uncited answer is not grounded."""
        return self.valid / self.total if self.total else 0.0


def check_citations(answer: str, sources: Sequence[Source]) -> CitationValidity:
    """Verify each token against the provided source tokens, exactly.

    Exact because the token carries its own paragraph range: `ds#0-4` and
    `ds#0-3` are different claims, and accepting a near miss would hide a model
    that invented a range it never saw.
    """
    allowed = {source.citation for source in sources}
    citations = parse_citations(answer)
    invalid = [citation.token for citation in citations if citation.token not in allowed]
    return CitationValidity(
        total=len(citations),
        valid=len(citations) - len(invalid),
        invalid=tuple(invalid),
    )


# ── LLM-as-judge ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class JudgeScore:
    """One judge's verdict. `normalized` is the 0-1 form used for averaging."""

    score: int
    verdict: bool
    reason: str
    issues: tuple[str, ...] = ()

    @property
    def normalized(self) -> float:
        span = JUDGE_SCORE_MAX - JUDGE_SCORE_MIN
        return (self.score - JUDGE_SCORE_MIN) / span


@dataclass(frozen=True)
class AnswerJudgement:
    """Everything measured about one generated answer."""

    case_id: str
    question: str
    answer: str
    faithfulness: JudgeScore
    relevance: JudgeScore
    citation_correctness: JudgeScore
    grounding: QuoteGrounding
    citation_validity: CitationValidity
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "faithfulness": self.faithfulness.score,
            "relevance": self.relevance.score,
            "citation_correctness": self.citation_correctness.score,
            "quotes": self.grounding.total,
            "quotes_grounded": self.grounding.grounded,
            "citations": self.citation_validity.total,
            "citations_valid": self.citation_validity.valid,
            "error": self.error,
        }


def _coerce_score(value: Any) -> int:
    """Clamp a model-supplied score into 1-5. Raise if it is not a number."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidResponseError(f"score is not a number: {value!r}")
    return max(JUDGE_SCORE_MIN, min(JUDGE_SCORE_MAX, round(float(value))))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [collapse_whitespace(item) for item in value if isinstance(item, str) and item.strip()]


@dataclass
class _JudgeSpec:
    system: str
    schema_name: str
    schema: dict[str, Any]
    verdict_key: str
    issues_key: str


_FAITHFULNESS = _JudgeSpec(
    system=(
        "You are a strict evaluator of retrieval-augmented answers. You are given "
        "sources and an answer. Decide whether every factual claim in the answer "
        "is supported by the sources. A claim that is true but absent from the "
        "sources is unsupported. Paraphrase is fine; new facts, names, numbers or "
        "causality are not. Score 5 if fully supported, 1 if largely invented."
    ),
    schema_name="faithfulness",
    schema={
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5},
            "supported": {"type": "boolean"},
            "unsupported_claims": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["score", "supported", "unsupported_claims", "reason"],
        "additionalProperties": False,
    },
    verdict_key="supported",
    issues_key="unsupported_claims",
)

_RELEVANCE = _JudgeSpec(
    system=(
        "You are a strict evaluator of answer relevance. Decide whether the "
        "answer actually addresses the question asked: directly, specifically and "
        "without padding. A correct-looking answer to a different question is "
        "irrelevant. Score 5 if it answers fully, 1 if it does not answer."
    ),
    schema_name="relevance",
    schema={
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5},
            "answered": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["score", "answered", "reason"],
        "additionalProperties": False,
    },
    verdict_key="answered",
    issues_key="",
)

_CITATION_CORRECTNESS = _JudgeSpec(
    system=(
        "You are a strict evaluator of citations. The answer cites sources with "
        "tokens like [ds#0-4]. For each citation, decide whether the cited source "
        "actually supports the sentence it is attached to. A citation that points "
        "at an unrelated passage is incorrect even if the passage exists. Score 5 "
        "if every citation supports its claim, 1 if they generally do not."
    ),
    schema_name="citation_correctness",
    schema={
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5},
            "correct": {"type": "boolean"},
            "incorrect_citations": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["score", "correct", "incorrect_citations", "reason"],
        "additionalProperties": False,
    },
    verdict_key="correct",
    issues_key="incorrect_citations",
)


def _validate(spec: _JudgeSpec, parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise InvalidResponseError("judge response was not a JSON object")
    return {
        "score": _coerce_score(parsed.get("score")),
        "verdict": bool(parsed.get(spec.verdict_key)),
        "reason": collapse_whitespace(parsed.get("reason") or ""),
        "issues": _string_list(parsed.get(spec.issues_key)) if spec.issues_key else [],
    }


async def _run_judge(
    spec: _JudgeSpec,
    *,
    user: str,
    client: OpenRouterClient,
    http: httpx.AsyncClient,
    temperature: float,
    seed: int,
) -> JudgeScore:
    parsed = await client.chat_json(
        system=spec.system,
        user=user,
        schema=spec.schema,
        schema_name=spec.schema_name,
        app_title="Ask Graham eval judge",
        client=http,
        validate=lambda value: _validate(spec, value),
        temperature=temperature,
        seed=seed,
    )
    return JudgeScore(
        score=parsed["score"],
        verdict=parsed["verdict"],
        reason=parsed["reason"],
        issues=tuple(parsed["issues"]),
    )


def _sources_block(sources: Sequence[Source]) -> str:
    return build_context(sources) if sources else "(no sources retrieved)"


async def _with_timeout(factory: Callable[[], Awaitable[JudgeScore]]) -> JudgeScore:
    """Bound one judge call, retrying once on a stall.

    The provider occasionally stalls mid-response, and httpx's read timeout does
    not always fire. `asyncio.wait_for` guarantees the eval cannot hang; the
    retry means a single stall costs one extra call rather than a lost data
    point. The factory (not a coroutine) is required because a cancelled
    coroutine cannot be awaited again.
    """
    last: TimeoutError | None = None
    for _ in range(2):
        try:
            return await asyncio.wait_for(factory(), timeout=settings.eval_request_timeout_s)
        except TimeoutError as exc:
            last = exc
            log.warning("eval.judge_timeout", timeout_s=settings.eval_request_timeout_s)
    assert last is not None
    raise last


async def judge_faithfulness(
    *,
    question: str,
    answer: str,
    sources: Sequence[Source],
    client: OpenRouterClient,
    http: httpx.AsyncClient,
    temperature: float,
    seed: int,
) -> JudgeScore:
    user = f"Sources:\n\n{_sources_block(sources)}\n\n---\nQuestion: {question}\n\nAnswer: {answer}"
    return await _run_judge(
        _FAITHFULNESS, user=user, client=client, http=http, temperature=temperature, seed=seed
    )


async def judge_relevance(
    *,
    question: str,
    answer: str,
    client: OpenRouterClient,
    http: httpx.AsyncClient,
    temperature: float,
    seed: int,
) -> JudgeScore:
    user = f"Question: {question}\n\nAnswer: {answer}"
    return await _run_judge(
        _RELEVANCE, user=user, client=client, http=http, temperature=temperature, seed=seed
    )


async def judge_citation_correctness(
    *,
    question: str,
    answer: str,
    sources: Sequence[Source],
    client: OpenRouterClient,
    http: httpx.AsyncClient,
    temperature: float,
    seed: int,
) -> JudgeScore:
    user = f"Sources:\n\n{_sources_block(sources)}\n\n---\nQuestion: {question}\n\nAnswer: {answer}"
    return await _run_judge(
        _CITATION_CORRECTNESS,
        user=user,
        client=client,
        http=http,
        temperature=temperature,
        seed=seed,
    )


async def judge_answer(
    *,
    case_id: str,
    question: str,
    answer: str,
    sources: Sequence[Source],
    client: OpenRouterClient,
    http: httpx.AsyncClient,
    temperature: float,
    seed: int,
) -> AnswerJudgement:
    """All five answer metrics for one answer.

    The deterministic checks always run. The three judge calls run concurrently —
    they are independent, network bound, and each is slow on a long answer — and
    a failure is recorded on the judgement rather than raised, so one bad case
    cannot discard the run.
    """
    grounding = ground_quotes(answer, sources)
    validity = check_citations(answer, sources)

    def as_score(value: JudgeScore | BaseException, label: str) -> JudgeScore:
        if isinstance(value, JudgeScore):
            return value
        detail = f"{type(value).__name__}: {value}".strip().rstrip(":")
        log.warning("eval.judge_failed", case_id=case_id, judge=label, error=detail[:200])
        return JudgeScore(0, False, f"judge failed: {detail}"[:200])

    raw = await asyncio.gather(
        _with_timeout(
            lambda: judge_faithfulness(
                question=question,
                answer=answer,
                sources=sources,
                client=client,
                http=http,
                temperature=temperature,
                seed=seed,
            )
        ),
        _with_timeout(
            lambda: judge_relevance(
                question=question,
                answer=answer,
                client=client,
                http=http,
                temperature=temperature,
                seed=seed,
            )
        ),
        _with_timeout(
            lambda: judge_citation_correctness(
                question=question,
                answer=answer,
                sources=sources,
                client=client,
                http=http,
                temperature=temperature,
                seed=seed,
            )
        ),
        return_exceptions=True,
    )
    faithfulness = as_score(raw[0], "faithfulness")
    relevance = as_score(raw[1], "relevance")
    citation_correctness = as_score(raw[2], "citation_correctness")
    failed = [
        name
        for name, value in zip(("faithfulness", "relevance", "citation"), raw, strict=True)
        if not isinstance(value, JudgeScore)
    ]

    return AnswerJudgement(
        case_id=case_id,
        question=question,
        answer=answer,
        faithfulness=faithfulness,
        relevance=relevance,
        citation_correctness=citation_correctness,
        grounding=grounding,
        citation_validity=validity,
        error=", ".join(failed) if failed else None,
    )


@dataclass
class AnswerMetrics:
    """Aggregate answer quality across cases. Rates and means are 0-1."""

    count: int = 0
    faithfulness: float = 0.0
    relevance: float = 0.0
    citation_correctness: float = 0.0
    quote_grounding: float = 0.0
    citation_precision: float = 0.0
    quotes: int = 0
    grounded_quotes: int = 0
    citations: int = 0
    valid_citations: int = 0
    failures: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "faithfulness": round(self.faithfulness, 4),
            "relevance": round(self.relevance, 4),
            "citation_correctness": round(self.citation_correctness, 4),
            "quote_grounding": round(self.quote_grounding, 4),
            "citation_precision": round(self.citation_precision, 4),
            "quotes": self.quotes,
            "grounded_quotes": self.grounded_quotes,
            "citations": self.citations,
            "valid_citations": self.valid_citations,
            "failures": self.failures,
        }


def aggregate_judgements(rows: Sequence[AnswerJudgement]) -> AnswerMetrics:
    """Aggregate answer quality across cases.

    Two deliberate choices, both about not letting a missing measurement read as
    a bad one:

    - **Judge scores are averaged per metric**, over the cases where that judge
      returned a score. A citation judge that timed out should not also drag down
      the faithfulness mean for that case.
    - **Grounding rates are micro-averaged** over the quoted spans and citation
      tokens that exist. An answer that quoted nothing is not evidence of a
      hallucinated quote, and counting it as a zero would punish brevity rather
      than dishonesty.
    """

    def mean(values: Sequence[JudgeScore]) -> float:
        scored = [value.normalized for value in values if value.score > 0]
        return sum(scored) / len(scored) if scored else 0.0

    quotes = sum(row.grounding.total for row in rows)
    grounded = sum(row.grounding.grounded for row in rows)
    citations = sum(row.citation_validity.total for row in rows)
    valid = sum(row.citation_validity.valid for row in rows)
    return AnswerMetrics(
        count=len(rows),
        faithfulness=mean([row.faithfulness for row in rows]),
        relevance=mean([row.relevance for row in rows]),
        citation_correctness=mean([row.citation_correctness for row in rows]),
        quote_grounding=grounded / quotes if quotes else 0.0,
        citation_precision=valid / citations if citations else 0.0,
        quotes=quotes,
        grounded_quotes=grounded,
        citations=citations,
        valid_citations=valid,
        failures=sum(1 for row in rows if row.error is not None),
    )


__all__ = [
    "AnswerJudgement",
    "AnswerMetrics",
    "Citation",
    "CitationValidity",
    "JudgeScore",
    "QuoteGrounding",
    "aggregate_judgements",
    "check_citations",
    "extract_quotes",
    "ground_quotes",
    "judge_answer",
    "judge_citation_correctness",
    "judge_faithfulness",
    "judge_relevance",
    "normalize_text",
    "parse_citations",
]
