"""Eval runner: dataset validation, variant aggregation and report rendering.

No database and no model here. The retrieval loop and the answer loop need both,
and are exercised by `cli.py eval`; what is tested here is everything that decides
what those numbers *mean*.
"""

import json
from pathlib import Path

import pytest

from config import REPO_ROOT
from core.errors import ValidationError
from eval.judges import AnswerMetrics
from eval.metrics import RankingMetrics
from eval.runner import (
    DEFAULT_DATASET,
    DEFAULT_VARIANTS,
    CaseMetrics,
    EvalConfig,
    EvalReport,
    RetrievalVariant,
    VariantReport,
    build_variants,
    dataset_digest,
    display_path,
    git_revision,
    load_cases,
    render_markdown,
)
from rag.retrieval import SearchHit


def _hit(slug: str, start: int = 0, end: int = 0, score: float = 1.0) -> SearchHit:
    return SearchHit(
        slug=slug,
        title=slug.title(),
        date=None,
        reading_time_min=1,
        text="x",
        score=score,
        start_paragraph=start,
        end_paragraph=end,
    )


# ── dataset loading ───────────────────────────────────────────────────


def _write(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "qa.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def _row(case_id: str = "c1", **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": case_id,
        "question": "do things",
        "slug": "ds",
        "group": "title",
    }
    row.update(overrides)
    return row


def test_load_cases_reads_jsonl(tmp_path: Path) -> None:
    path = _write(tmp_path, [_row("a"), _row("b", slug="do", paragraphs=[0, 1])])
    cases = load_cases(path)
    assert [case.id for case in cases] == ["a", "b"]
    assert cases[1].paragraphs == (0, 1)
    assert cases[1].slug == "do"


def test_load_cases_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    path = tmp_path / "qa.jsonl"
    path.write_text(
        "\n// a note\n" + json.dumps(_row()) + "\n\n",
        encoding="utf-8",
    )
    # The `//` line is not valid JSON; it must be skipped, not fail.
    cases = load_cases(path)
    assert len(cases) == 1


def test_load_cases_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = _write(tmp_path, [_row("dup"), _row("dup")])
    with pytest.raises(ValidationError, match="duplicate id"):
        load_cases(path)


def test_load_cases_requires_the_key_fields(tmp_path: Path) -> None:
    path = _write(tmp_path, [{"id": "a", "question": "", "slug": "ds"}])
    with pytest.raises(ValidationError, match="required"):
        load_cases(path)


def test_load_cases_rejects_bad_paragraphs(tmp_path: Path) -> None:
    path = _write(tmp_path, [_row(paragraphs=[0, -1])])
    with pytest.raises(ValidationError, match="paragraphs"):
        load_cases(path)


def test_load_cases_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "qa.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="invalid JSON"):
        load_cases(path)


def test_load_cases_missing_file_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="not found"):
        load_cases(tmp_path / "nope.jsonl")


def test_dataset_digest_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    path = _write(tmp_path, [_row("a")])
    first = dataset_digest(path)
    assert first == dataset_digest(path)
    path.write_text(json.dumps(_row("b")) + "\n", encoding="utf-8")
    assert dataset_digest(path) != first


# ── the committed dataset ─────────────────────────────────────────────


def test_committed_dataset_has_enough_cases() -> None:
    cases = load_cases(DEFAULT_DATASET)
    assert len(cases) >= 30


def test_committed_dataset_slugs_exist_in_the_corpus() -> None:
    known = {entry["slug"] for entry in json.loads((REPO_ROOT / "data" / "index.json").read_text())}
    unknown = sorted({case.slug for case in load_cases(DEFAULT_DATASET)} - known)
    assert unknown == [], f"gold slugs not in the corpus: {unknown}"


def test_committed_dataset_ids_are_unique() -> None:
    cases = load_cases(DEFAULT_DATASET)
    assert len({case.id for case in cases}) == len(cases)


def test_committed_dataset_is_tagged_by_group() -> None:
    cases = load_cases(DEFAULT_DATASET)
    groups = {case.group for case in cases}
    assert {"title", "paraphrase"} <= groups


def test_committed_dataset_paragraph_refs_are_in_range() -> None:
    for case in load_cases(DEFAULT_DATASET):
        if not case.paragraphs:
            continue
        essay = json.loads((REPO_ROOT / "data" / "essays" / f"{case.slug}.json").read_text())
        assert max(case.paragraphs) < len(essay["paragraphs"]), case.id


# ── variants and aggregation ──────────────────────────────────────────


def test_build_variants_includes_the_primary_when_new() -> None:
    variants = build_variants("vector", True)
    assert any(v.mode == "vector" and v.rerank for v in variants)
    assert len(variants) == len(DEFAULT_VARIANTS) + 1


def test_build_variants_does_not_duplicate_a_default() -> None:
    variants = build_variants("hybrid", True)
    assert sum(1 for v in variants if v.mode == "hybrid" and v.rerank) == 1
    assert len(variants) == len(DEFAULT_VARIANTS)


def _case_metrics(
    case_id: str,
    *,
    group: str = "title",
    gold: str = "ds",
    found_at: int | None = 1,
    coverage: float | None = None,
) -> CaseMetrics:
    hits = [_hit("other"), _hit(gold), _hit("other2")]
    if found_at is None:
        hits = [_hit("other"), _hit("other2")]
    metrics = RankingMetrics(
        recall=1.0 if found_at else 0.0,
        mrr=1.0 / found_at if found_at else 0.0,
        ndcg=1.0 if found_at == 1 else 0.0,
    )
    return CaseMetrics(
        case_id=case_id,
        question="q",
        group=group,
        gold_slug=gold,
        metrics=metrics,
        coverage=coverage,
        hits=hits,
    )


def test_variant_overall_averages_cases() -> None:
    report = VariantReport(
        variant=RetrievalVariant("v", "hybrid", False),
        cases=[
            _case_metrics("a", found_at=1),
            _case_metrics("b", found_at=None),
        ],
    )
    overall = report.overall()
    assert overall.recall == 0.5
    assert overall.mrr == 0.5


def test_variant_by_group_splits_cases() -> None:
    report = VariantReport(
        variant=RetrievalVariant("v", "hybrid", False),
        cases=[
            _case_metrics("a", group="title", found_at=1),
            _case_metrics("b", group="paraphrase", found_at=None),
        ],
    )
    groups = report.by_group()
    assert set(groups) == {"title", "paraphrase"}
    assert groups["title"].recall == 1.0
    assert groups["paraphrase"].recall == 0.0


def test_variant_coverage_ignores_cases_without_paragraphs() -> None:
    report = VariantReport(
        variant=RetrievalVariant("v", "hybrid", False),
        cases=[_case_metrics("a", coverage=1.0), _case_metrics("b", coverage=None)],
    )
    mean, n = report.coverage()
    assert mean == 1.0
    assert n == 1


def test_variant_misses_lists_only_failed_cases() -> None:
    report = VariantReport(
        variant=RetrievalVariant("v", "hybrid", False),
        cases=[_case_metrics("a", found_at=1), _case_metrics("b", found_at=None)],
    )
    assert [case.case_id for case in report.misses()] == ["b"]


# ── report rendering ──────────────────────────────────────────────────


def _config() -> EvalConfig:
    return EvalConfig(
        dataset="eval/datasets/qa.jsonl",
        dataset_sha256="abc123def456",
        cases=2,
        k=10,
        mode="hybrid",
        rerank=True,
        generation_model="openai/gpt-oss-120b",
        judge_model="openai/gpt-oss-120b",
        temperature=0.0,
        seed=7,
        rrf_k=60,
        title_boost=3.0,
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_dim=384,
        chunk_max_tokens=384,
        chunk_overlap_tokens=64,
        git_revision="deadbee",
        generated_at="2026-10-13T00:00:00Z",
    )


def _report(*, answers: AnswerMetrics | None = None) -> EvalReport:
    variants = [
        VariantReport(
            variant=RetrievalVariant("hybrid (rerank off)", "hybrid", False),
            cases=[_case_metrics("a"), _case_metrics("b", found_at=None)],
        ),
        VariantReport(
            variant=RetrievalVariant("hybrid (rerank on)", "hybrid", True),
            cases=[_case_metrics("a"), _case_metrics("b", found_at=2)],
        ),
    ]
    return EvalReport(config=_config(), variants=variants, primary=variants[1], answers=answers)


def test_render_includes_config_provenance() -> None:
    text = render_markdown(_report())
    assert "deadbee" in text
    assert "abc123def456" in text
    assert "`openai/gpt-oss-120b`" in text
    assert "temperature" in text.lower()


def test_render_includes_the_ablation_table() -> None:
    text = render_markdown(_report())
    assert "hybrid (rerank off)" in text
    assert "hybrid (rerank on)" in text
    assert "recall@10" in text
    assert "nDCG@10" in text


def test_render_marks_answers_not_run() -> None:
    text = render_markdown(_report())
    assert "Not run" in text


def test_render_includes_answer_metrics_when_present() -> None:
    metrics = AnswerMetrics(
        count=2,
        faithfulness=1.0,
        relevance=0.75,
        citation_correctness=0.5,
        quote_grounding=1.0,
        citation_precision=0.5,
        quotes=2,
        citations=2,
    )
    text = render_markdown(_report(answers=metrics))
    assert "faithfulness (LLM judge)" in text
    assert "quote grounding (verbatim)" in text
    assert "Per-case answers" in text


def test_render_lists_retrieval_failures_for_phase_8() -> None:
    variants = [
        VariantReport(
            variant=RetrievalVariant("hybrid (rerank off)", "hybrid", False),
            cases=[_case_metrics("a", found_at=1), _case_metrics("b", found_at=None)],
        )
    ]
    report = EvalReport(config=_config(), variants=variants, primary=variants[0])
    text = render_markdown(report)
    assert "Retrieval failures" in text
    assert "not" in text and "retrieved in the top 10" in text
    assert "`ds`" in text


def test_git_revision_is_a_string() -> None:
    assert isinstance(git_revision(), str) and git_revision()


def test_git_revision_honors_the_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The container has no git; the caller passes the commit it built from."""
    monkeypatch.setenv("GIT_REVISION", "abc1234")
    assert git_revision() == "abc1234"


def test_display_path_is_backend_relative() -> None:
    assert display_path(DEFAULT_DATASET) == "backend/eval/datasets/qa.jsonl"


def test_display_path_falls_back_outside_the_backend(tmp_path: Path) -> None:
    assert display_path(tmp_path / "qa.jsonl") == str(tmp_path / "qa.jsonl")
