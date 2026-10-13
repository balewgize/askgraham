"""The eval runner: dataset in, a baseline report out.

    uv run python cli.py eval                 # retrieval only — no API cost
    uv run python cli.py eval --answers        # generate + judge answers (pays)
    uv run python cli.py eval --limit 8        # smoke run

Two phases, split where the constraints are:

1. **Retrieval** runs every question against every variant, sequentially. It is
   cheap (~50ms) but it needs the request's `AsyncSession`, and one session must
   not have two queries in flight — so concurrency here would be a bug, not a
   speed-up.
2. **Answers** are generated and judged concurrently, because they are network
   bound and order-independent. The retrieval results are already in hand, so a
   worker never touches the session.

The report is a pure rendering of the dataclasses below, so the format is
testable without a database or a model — which is the only way a results file can
be trusted to say what the run did.
"""

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from config import BACKEND_DIR, REPO_ROOT, settings
from core.errors import ValidationError
from core.logging_config import log
from eval.judges import (
    AnswerJudgement,
    AnswerMetrics,
    CitationValidity,
    JudgeScore,
    QuoteGrounding,
    aggregate_judgements,
    judge_answer,
)
from eval.metrics import RankingMetrics, evaluate_ranking, mean_rankings, paragraph_coverage
from llm.client import OpenRouterClient, map_bounded
from llm.generation import Source, stream_answer
from rag.retrieval import RetrievalMode, SearchHit, hybrid_search

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = EVAL_DIR / "datasets" / "qa.jsonl"
DEFAULT_REPORT = EVAL_DIR / "results" / "baseline.md"

# Fetch more chunks than `k` so collapsing them to essays still leaves `k`
# distinct ones. Matches what the search endpoint does when it dedupes.
_FETCH_MULTIPLIER = 3


# ── dataset ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvalCase:
    """One hand-authored question and the essay it must retrieve.

    `paragraphs` is optional and deliberately separate from `slug`: the slug is
    the answer, the paragraphs are the supporting passage. They are graded
    differently because they support different claims — "did it find the essay"
    and "did it find the part of the essay".
    """

    id: str
    question: str
    slug: str
    group: str
    paragraphs: tuple[int, ...] = ()
    notes: str = ""


def load_cases(path: Path) -> list[EvalCase]:
    """Read and validate the JSONL dataset. A malformed line fails the run.

    Validating here rather than tolerating bad rows keeps the metric honest: a
    silently dropped question would just look like an easier dataset.
    """
    if not path.is_file():
        raise ValidationError(f"eval dataset not found: {path}")

    cases: list[EvalCase] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{path.name}:{number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValidationError(f"{path.name}:{number}: expected a JSON object")

        case_id = str(row.get("id") or "").strip()
        question = str(row.get("question") or "").strip()
        slug = str(row.get("slug") or "").strip()
        if not case_id or not question or not slug:
            raise ValidationError(f"{path.name}:{number}: id, question and slug are required")
        if case_id in seen:
            raise ValidationError(f"{path.name}:{number}: duplicate id {case_id!r}")
        seen.add(case_id)

        paragraphs = row.get("paragraphs") or []
        if not isinstance(paragraphs, list) or any(
            not isinstance(p, int) or isinstance(p, bool) or p < 0 for p in paragraphs
        ):
            raise ValidationError(
                f"{path.name}:{number}: paragraphs must be a list of non-negative ints"
            )

        cases.append(
            EvalCase(
                id=case_id,
                question=question,
                slug=slug,
                group=str(row.get("group") or "uncategorized").strip() or "uncategorized",
                paragraphs=tuple(sorted(set(paragraphs))),
                notes=str(row.get("notes") or "").strip(),
            )
        )

    if not cases:
        raise ValidationError(f"{path.name}: no cases")
    return cases


def dataset_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── retrieval evaluation ──────────────────────────────────────────────


@dataclass(frozen=True)
class RetrievalVariant:
    """One configuration of the first-stage + rerank pipeline."""

    label: str
    mode: RetrievalMode
    rerank: bool


DEFAULT_VARIANTS: tuple[RetrievalVariant, ...] = (
    RetrievalVariant("hybrid (rerank off)", "hybrid", False),
    RetrievalVariant("hybrid (rerank on)", "hybrid", True),
    RetrievalVariant("vector only", "vector", False),
    RetrievalVariant("lexical only", "lexical", False),
)


def primary_variant(mode: RetrievalMode, rerank: bool) -> RetrievalVariant:
    return RetrievalVariant("primary", mode, rerank)


def build_variants(mode: RetrievalMode, rerank: bool) -> list[RetrievalVariant]:
    """The default ablation set, with the configured primary appended if new."""
    variants = list(DEFAULT_VARIANTS)
    if not any(v.mode == mode and v.rerank == rerank for v in variants):
        variants.append(primary_variant(mode, rerank))
    return variants


@dataclass
class CaseMetrics:
    """One case under one variant: its ranking score and its retrieved hits."""

    case_id: str
    question: str
    group: str
    gold_slug: str
    metrics: RankingMetrics
    coverage: float | None
    hits: list[SearchHit]

    @property
    def gold_rank(self) -> int | None:
        """1-based rank of the first chunk from the gold essay, or None."""
        for rank, hit in enumerate(self.hits, start=1):
            if hit.slug == self.gold_slug:
                return rank
        return None


def _dedupe_slugs(hits: Sequence[SearchHit]) -> list[str]:
    """Essay order, first (best) chunk wins. Mirrors the palette's dedupe."""
    seen: set[str] = set()
    out: list[str] = []
    for hit in hits:
        if hit.slug not in seen:
            seen.add(hit.slug)
            out.append(hit.slug)
    return out


async def evaluate_variant(
    session: AsyncSession,
    cases: Sequence[EvalCase],
    variant: RetrievalVariant,
    *,
    k: int,
) -> list[CaseMetrics]:
    """Rank every case for one variant. Sequential by necessity (see module doc)."""
    fetch = min(settings.search_max_limit, max(k, k * _FETCH_MULTIPLIER))
    results: list[CaseMetrics] = []
    for case in cases:
        search = await hybrid_search(
            session, case.question, limit=fetch, mode=variant.mode, rerank=variant.rerank
        )
        hits = search.hits
        gains = [1.0 if slug == case.slug else 0.0 for slug in _dedupe_slugs(hits)]
        metrics = evaluate_ranking(gains, k=k, n_relevant=1, ideal_gains=[1.0])
        coverage = (
            paragraph_coverage(
                [(hit.start_paragraph, hit.end_paragraph) for hit in hits],
                case.paragraphs,
                k,
            )
            if case.paragraphs
            else None
        )
        results.append(
            CaseMetrics(
                case_id=case.id,
                question=case.question,
                group=case.group,
                gold_slug=case.slug,
                metrics=metrics,
                coverage=coverage,
                hits=list(hits),
            )
        )
    return results


@dataclass
class VariantReport:
    variant: RetrievalVariant
    cases: list[CaseMetrics]

    def overall(self) -> RankingMetrics:
        return mean_rankings([case.metrics for case in self.cases])

    def by_group(self) -> dict[str, RankingMetrics]:
        grouped: dict[str, list[RankingMetrics]] = {}
        for case in self.cases:
            grouped.setdefault(case.group, []).append(case.metrics)
        return {group: mean_rankings(rows) for group, rows in sorted(grouped.items())}

    def coverage(self) -> tuple[float, int]:
        """Mean paragraph coverage and the number of cases that have paragraphs."""
        rows = [case.coverage for case in self.cases if case.coverage is not None]
        if not rows:
            return 0.0, 0
        return sum(rows) / len(rows), len(rows)

    def misses(self) -> list[CaseMetrics]:
        """Cases where the gold essay was not in the head — Phase 8's raw material."""
        return [case for case in self.cases if case.metrics.recall <= 0.0]


# ── answer evaluation ─────────────────────────────────────────────────


def _to_sources(hits: Sequence[SearchHit], limit: int) -> list[Source]:
    return [
        Source(
            slug=hit.slug,
            title=hit.title,
            start_paragraph=hit.start_paragraph,
            end_paragraph=hit.end_paragraph,
            text=hit.text,
        )
        for hit in hits[:limit]
    ]


async def generate_answer(
    *,
    question: str,
    sources: Sequence[Source],
    client: OpenRouterClient,
    temperature: float,
    seed: int,
    usage: dict[str, int],
) -> str:
    chunks: list[str] = []
    async for delta in stream_answer(
        question=question,
        history=[],
        sources=sources,
        client=client,
        usage=usage,
        temperature=temperature,
        seed=seed,
    ):
        chunks.append(delta)
    return "".join(chunks)


def _failed_judgement(case_id: str, question: str, error: Exception) -> AnswerJudgement:
    reason = str(error)[:200]
    failed = JudgeScore(0, False, reason)
    return AnswerJudgement(
        case_id=case_id,
        question=question,
        answer="",
        faithfulness=failed,
        relevance=failed,
        citation_correctness=failed,
        grounding=QuoteGrounding(total=0, grounded=0),
        citation_validity=CitationValidity(total=0, valid=0),
        error=reason,
    )


async def evaluate_answers(
    *,
    cases: Sequence[EvalCase],
    hits_by_case: dict[str, list[SearchHit]],
    gen_client: OpenRouterClient,
    judge_client: OpenRouterClient,
    temperature: float,
    seed: int,
    concurrency: int,
) -> list[AnswerJudgement]:
    """Generate and judge an answer per case, concurrently."""
    if not gen_client.configured or not judge_client.configured:
        raise ValidationError("OPENROUTER_API_KEY is not set; cannot evaluate answers")

    context_chunks = max(1, settings.chat_context_chunks)

    async with httpx.AsyncClient(follow_redirects=True) as http:

        async def one(case: EvalCase) -> AnswerJudgement:
            sources = _to_sources(hits_by_case.get(case.id, []), context_chunks)
            usage: dict[str, int] = {}
            try:
                answer = await generate_answer(
                    question=case.question,
                    sources=sources,
                    client=gen_client,
                    temperature=temperature,
                    seed=seed,
                    usage=usage,
                )
            except Exception as exc:
                log.warning("eval.generation_failed", case_id=case.id, error=str(exc)[:200])
                return _failed_judgement(case.id, case.question, exc)
            log.info(
                "eval.answer", case_id=case.id, chars=len(answer), sources=len(sources), **usage
            )
            return await judge_answer(
                case_id=case.id,
                question=case.question,
                answer=answer,
                sources=sources,
                client=judge_client,
                http=http,
                temperature=temperature,
                seed=seed,
            )

        results = await map_bounded(cases, one, concurrency=max(1, concurrency))

    judgements: list[AnswerJudgement] = []
    for case, result, error in results:
        if error is not None:
            judgements.append(_failed_judgement(case.id, case.question, error))
        else:
            judgements.append(result)  # map_bounded erases each item's type
    return judgements


# ── the run and its report ────────────────────────────────────────────


@dataclass(frozen=True)
class EvalConfig:
    dataset: str
    dataset_sha256: str
    cases: int
    k: int
    mode: str
    rerank: bool
    generation_model: str
    judge_model: str
    temperature: float
    seed: int
    rrf_k: int
    title_boost: float
    embedding_model: str
    embedding_dim: int
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    git_revision: str
    generated_at: str


@dataclass
class EvalReport:
    config: EvalConfig
    variants: list[VariantReport]
    primary: VariantReport
    answers: AnswerMetrics | None = None
    judgements: list[AnswerJudgement] = field(default_factory=list)


def git_revision() -> str:
    """Short commit hash, or `GIT_REVISION` when set.

    The override exists because the API container has no `git` binary and does
    not mount `.git` — the image stays small and the repo stays out of it. The
    caller sets the variable so the committed baseline still names its commit.
    """
    override = os.environ.get("GIT_REVISION", "").strip()
    if override:
        return override
    try:
        completed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def display_path(path: Path) -> str:
    """A stable, readable path for the report, independent of the mount root.

    The container sees the backend at `/app` and the repo root at `/`, so a
    repo-relative path reads `app/eval/...` there. Backend-relative, prefixed,
    reads `backend/eval/...` everywhere.
    """
    try:
        return f"backend/{path.resolve().relative_to(BACKEND_DIR)}"
    except ValueError:
        return str(path)


async def run_eval(
    session: AsyncSession,
    *,
    dataset: Path = DEFAULT_DATASET,
    k: int | None = None,
    mode: RetrievalMode = "hybrid",
    rerank: bool | None = None,
    limit: int | None = None,
    answers: bool = False,
    generation_model: str | None = None,
    judge_model: str | None = None,
    variants: Sequence[RetrievalVariant] | None = None,
) -> EvalReport:
    """Run retrieval (always) and answers (opt-in) and return the report."""
    cutoff = k or settings.eval_k
    use_rerank = settings.rerank_enabled if rerank is None else rerank
    cases = load_cases(dataset)
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        raise ValidationError("no cases selected")

    variant_list = list(variants) if variants is not None else build_variants(mode, use_rerank)
    reports: list[VariantReport] = []
    for variant in variant_list:
        started = time.perf_counter()
        case_metrics = await evaluate_variant(session, cases, variant, k=cutoff)
        report = VariantReport(variant=variant, cases=case_metrics)
        reports.append(report)
        log.info(
            "eval.variant_done",
            variant=variant.label,
            recall=round(report.overall().recall, 4),
            mrr=round(report.overall().mrr, 4),
            ndcg=round(report.overall().ndcg, 4),
            elapsed_s=round(time.perf_counter() - started, 2),
        )

    def find_primary() -> VariantReport:
        for report in reports:
            if report.variant.mode == mode and report.variant.rerank == use_rerank:
                return report
        return reports[0]

    primary = find_primary()
    config = EvalConfig(
        dataset=display_path(dataset),
        dataset_sha256=dataset_digest(dataset)[:12],
        cases=len(cases),
        k=cutoff,
        mode=mode,
        rerank=use_rerank,
        generation_model=generation_model or settings.openrouter_model,
        judge_model=judge_model or settings.eval_judge_model_name,
        temperature=settings.eval_temperature,
        seed=settings.eval_seed,
        rrf_k=settings.rrf_k,
        title_boost=settings.title_boost,
        embedding_model=settings.embedding_model,
        embedding_dim=settings.embedding_dim,
        chunk_max_tokens=settings.chunk_max_tokens,
        chunk_overlap_tokens=settings.chunk_overlap_tokens,
        git_revision=git_revision(),
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    judgement_rows: list[AnswerJudgement] = []
    answer_metrics: AnswerMetrics | None = None
    if answers:
        judgement_rows = await evaluate_answers(
            cases=cases,
            hits_by_case={case.case_id: case.hits for case in primary.cases},
            gen_client=OpenRouterClient(model=config.generation_model),
            judge_client=OpenRouterClient(model=config.judge_model),
            temperature=config.temperature,
            seed=config.seed,
            concurrency=settings.eval_concurrency,
        )
        answer_metrics = aggregate_judgements(judgement_rows)
        log.info("eval.answers_done", **answer_metrics.as_dict())

    return EvalReport(
        config=config,
        variants=reports,
        primary=primary,
        answers=answer_metrics,
        judgements=judgement_rows,
    )


# ── rendering ─────────────────────────────────────────────────────────


def _row(cells: Sequence[object]) -> str:
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def _table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    lines = [_row(headers), "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend(_row(row) for row in rows)
    return lines


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def _score(value: int) -> str:
    """A judge score, or an em dash when the judge returned nothing.

    A real score is 1-5, so a 0 is always a failed or timed-out call. Rendering
    it as `0/5` would read as a verdict rather than a missing measurement.
    """
    return "—" if value <= 0 else str(value)


def render_markdown(report: EvalReport) -> str:
    """Render the whole report. Pure: same report in, same markdown out."""
    config = report.config
    lines: list[str] = []
    lines.append("# askgraham — Phase 7 eval baseline")
    lines.append("")
    lines.append(
        f"_Generated {config.generated_at} · commit `{config.git_revision}` · "
        f"`{config.dataset}` (sha256:{config.dataset_sha256}, {config.cases} cases)._"
    )
    lines.append("")
    lines.append(
        "Retrieval is measured at the **essay** level, the unit a reader (and the "
        "⌘K palette) cares about: recall@k is success@k for a single gold essay, "
        "MRR is the rank of the gold essay, and nDCG@k is its discounted gain. "
        "Paragraph recall@k is stricter — the fraction of the hand-labelled gold "
        "paragraphs actually covered by a retrieved chunk."
    )
    lines.append("")

    lines.append("## Configuration")
    lines.append("")
    lines.extend(
        _table(
            ["setting", "value"],
            [
                ["cutoff k", config.k],
                ["primary variant", f"{config.mode} · rerank={config.rerank}"],
                ["generation model", f"`{config.generation_model}`"],
                ["judge model", f"`{config.judge_model}`"],
                ["temperature / seed", f"{config.temperature} / {config.seed}"],
                ["RRF k / title boost", f"{config.rrf_k} / {config.title_boost}"],
                [
                    "embedding",
                    f"`{config.embedding_model}` ({config.embedding_dim}-dim)",
                ],
                [
                    "chunk max / overlap",
                    f"{config.chunk_max_tokens} / {config.chunk_overlap_tokens} tokens",
                ],
            ],
        )
    )
    lines.append("")

    lines.append("## Retrieval ablation (before → after)")
    lines.append("")
    has_coverage = any(v.coverage()[1] for v in report.variants)
    retrieval_rows: list[list[object]] = []
    for variant in report.variants:
        overall = variant.overall()
        coverage, coverage_n = variant.coverage()
        row: list[object] = [
            variant.variant.label,
            _fmt(overall.recall),
            _fmt(overall.mrr),
            _fmt(overall.ndcg),
        ]
        if has_coverage:
            row.append(f"{_fmt(coverage)} ({coverage_n})" if coverage_n else "—")
        retrieval_rows.append(row)
    headers = ["variant", f"recall@{config.k}", "MRR", f"nDCG@{config.k}"]
    if has_coverage:
        headers.append(f"paragraph recall@{config.k}")
    lines.extend(_table(headers, retrieval_rows))
    lines.append("")
    lines.extend(_ablation_notes(report))
    lines.append("")

    lines.append(f"### Retrieval by group — {report.primary.variant.label}")
    lines.append("")
    group_rows = [
        [
            group,
            sum(1 for case in report.primary.cases if case.group == group),
            _fmt(metrics.recall),
            _fmt(metrics.mrr),
            _fmt(metrics.ndcg),
        ]
        for group, metrics in report.primary.by_group().items()
    ]
    lines.extend(
        _table(["group", "n", f"recall@{config.k}", "MRR", f"nDCG@{config.k}"], group_rows)
    )
    lines.append("")

    misses = report.primary.misses()
    lines.append(f"### Retrieval failures — {report.primary.variant.label}")
    lines.append("")
    if not misses:
        lines.append(f"Every gold essay was retrieved in the top {config.k}.")
    else:
        lines.append(
            f"{len(misses)} of {len(report.primary.cases)} gold essays were **not** "
            f"retrieved in the top {config.k}. These are the cases Phase 8 tuning starts from."
        )
        lines.append("")
        lines.extend(
            _table(
                ["id", "group", "question", "gold essay"],
                [
                    [case.case_id, case.group, case.question, f"`{case.gold_slug}`"]
                    for case in misses
                ],
            )
        )
    lines.append("")

    lines.append("## Answer quality")
    lines.append("")
    if report.answers is None:
        lines.append(
            "_Not run. Re-run with `uv run python cli.py eval --answers` to generate "
            "and judge answers (costs money). The retrieval numbers above need no API key._"
        )
    else:
        metrics = report.answers
        lines.extend(
            _table(
                ["metric", "value (0-1)"],
                [
                    ["faithfulness (LLM judge)", _fmt(metrics.faithfulness)],
                    ["relevance (LLM judge)", _fmt(metrics.relevance)],
                    ["citation correctness (LLM judge)", _fmt(metrics.citation_correctness)],
                    ["quote grounding (verbatim)", _fmt(metrics.quote_grounding)],
                    ["citation precision (verbatim)", _fmt(metrics.citation_precision)],
                    ["answers judged", metrics.count],
                    [
                        "quoted spans grounded",
                        f"{metrics.grounded_quotes}/{metrics.quotes}",
                    ],
                    ["citations valid", f"{metrics.valid_citations}/{metrics.citations}"],
                    ["judge failures", metrics.failures],
                ],
            )
        )
        lines.append("")
        lines.append(
            "Faithfulness, relevance and citation correctness are 1-5 judge scores "
            "normalized to 0-1, averaged per metric over the cases where that judge "
            "returned a score. Quote grounding splits each quoted span on elisions and "
            "inline citation tokens and requires every fragment to appear verbatim in "
            "the retrieved sources; citation precision checks each `[slug#start-end]` "
            "token against the sources the model was given. Both are exact and cost "
            "nothing to run."
        )
        if metrics.failures:
            lines.append("")
            lines.append(
                f"{metrics.failures} case(s) had a judge call that failed or timed out. "
                f"Those scores are shown as `—` below and excluded from the means, so a "
                f"provider stall never reads as a low score."
            )
        lines.append("")
        lines.append("### Per-case answers")
        lines.append("")
        lines.extend(
            _table(
                ["id", "faith", "rel", "cite", "quotes", "citations", "answer (excerpt)"],
                [
                    [
                        judgement.case_id,
                        _score(judgement.faithfulness.score),
                        _score(judgement.relevance.score),
                        _score(judgement.citation_correctness.score),
                        f"{judgement.grounding.grounded}/{judgement.grounding.total}",
                        f"{judgement.citation_validity.valid}/{judgement.citation_validity.total}",
                        _excerpt(judgement.answer),
                    ]
                    for judgement in report.judgements
                ],
            )
        )
    lines.append("")

    lines.append("## Phase 8: tuning inputs")
    lines.append("")
    lines.append(
        "This file is the **before** column. Phase 8 sweeps these against it and appends the after:"
    )
    lines.append("")
    lines.append("- chunk size {512, 1024, 2048} and overlap")
    lines.append("- RRF k and the title boost (unmeasured here — the setting is shared)")
    lines.append("- reranker on/off and `RERANK_CANDIDATES` (priced in the table above)")
    lines.append("- query rewriting on/off for follow-ups")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _excerpt(text: str, limit: int = 80) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed or "—"
    return collapsed[:limit].rsplit(" ", 1)[0] + "…"


def _find(report: EvalReport, mode: str, rerank: bool) -> VariantReport | None:
    for variant in report.variants:
        if variant.variant.mode == mode and variant.variant.rerank == rerank:
            return variant
    return None


def _ablation_notes(report: EvalReport) -> list[str]:
    """Turn the table into a sentence or two, so the number is not just a number."""
    base = _find(report, "hybrid", False)
    reranked = _find(report, "hybrid", True)
    vector = _find(report, "vector", False)
    lexical = _find(report, "lexical", False)
    notes: list[str] = []

    def delta(a: float, b: float) -> str:
        return f"{b - a:+.3f}"

    if base is not None and reranked is not None:
        notes.append(
            f"- **Reranker:** MRR {delta(base.overall().mrr, reranked.overall().mrr)}, "
            f"nDCG@{report.config.k} {delta(base.overall().ndcg, reranked.overall().ndcg)}."
        )
    if base is not None and vector is not None:
        notes.append(
            f"- **Hybrid vs vector-only:** MRR {delta(vector.overall().mrr, base.overall().mrr)}, "
            f"nDCG@{report.config.k} {delta(vector.overall().ndcg, base.overall().ndcg)}."
        )
    if base is not None and lexical is not None:
        notes.append(
            f"- **Hybrid vs lexical-only:** MRR "
            f"{delta(lexical.overall().mrr, base.overall().mrr)}, nDCG@{report.config.k} "
            f"{delta(lexical.overall().ndcg, base.overall().ndcg)}."
        )
    return notes


def write_report(report: EvalReport, path: Path = DEFAULT_REPORT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
    return path


__all__ = [
    "DEFAULT_DATASET",
    "DEFAULT_REPORT",
    "DEFAULT_VARIANTS",
    "EVAL_DIR",
    "CaseMetrics",
    "EvalCase",
    "EvalConfig",
    "EvalReport",
    "RetrievalVariant",
    "VariantReport",
    "build_variants",
    "dataset_digest",
    "display_path",
    "evaluate_answers",
    "evaluate_variant",
    "git_revision",
    "load_cases",
    "render_markdown",
    "run_eval",
    "write_report",
]
