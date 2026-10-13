"""Essay classification.

The first test here is the important one. The cache key is derived from essay
text and the committed `data/phases.json` holds those values; if the derivation
drifts, the next run re-classifies all 233 essays and re-bills for them.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from config import settings
from core.errors import ValidationError
from llm.classify import (
    build_prompt,
    classify_essays,
    essay_cache_hash,
    load_existing,
    response_schema,
    validate_result,
    write_phases,
)
from llm.client import InvalidResponseError

TAXONOMY = {
    "version": 1,
    "phases": [
        {"id": "ideas", "label": "Ideas", "order": 1, "description": "Finding what to work on."},
        {"id": "any", "label": "Any stage", "order": 8, "description": "Not stage-specific."},
    ],
}

ESSAY: dict[str, Any] = {
    "slug": "demo",
    "title": "Demo",
    "date": "July 2009",
    "paragraphs": ["First para.", "Second para."],
}


# ── the money guard ───────────────────────────────────────────────────


def test_cache_hash_matches_every_committed_hash() -> None:
    """A drift here triggers a paid re-classification of the whole corpus."""
    phases = json.loads((settings.data_dir / "phases.json").read_text(encoding="utf-8"))
    essays = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in (settings.data_dir / "essays").glob("*.json")
    }

    mismatched = [
        slug
        for slug, value in phases["essays"].items()
        if essay_cache_hash(essays[slug]) != value["hash"]
    ]
    assert mismatched == [], f"cache key drifted for {mismatched[:5]}"
    assert len(phases["essays"]) == 233


def test_cache_hash_is_sha256_of_newline_joined_paragraphs() -> None:
    import hashlib

    expected = hashlib.sha256(b"First para.\nSecond para.").hexdigest()[:16]
    assert essay_cache_hash(ESSAY) == expected


def test_cache_hash_is_sensitive_to_whitespace() -> None:
    """Paragraph boundaries matter: joining with "" would collide."""
    a = {"paragraphs": ["ab", "c"]}
    b = {"paragraphs": ["a", "bc"]}
    assert essay_cache_hash(a) != essay_cache_hash(b)


def test_cache_hash_handles_no_paragraphs() -> None:
    assert essay_cache_hash({}) == essay_cache_hash({"paragraphs": []})


# ── prompts ───────────────────────────────────────────────────────────


def test_prompt_lists_every_phase_with_its_description() -> None:
    system, _ = build_prompt(ESSAY, TAXONOMY)
    assert "- ideas: Ideas — Finding what to work on." in system
    assert "- any: Any stage — Not stage-specific." in system


def test_prompt_user_block_carries_title_date_and_body() -> None:
    _, user = build_prompt(ESSAY, TAXONOMY)
    assert user.startswith("Title: Demo\nDate: July 2009\n\n")
    assert user.endswith("First para.\n\nSecond para.")


def test_prompt_uses_unknown_for_undated_essays() -> None:
    _, user = build_prompt({**ESSAY, "date": None}, TAXONOMY)
    assert "Date: unknown" in user


def test_prompt_wording_is_stable() -> None:
    """The wording was tuned against model output; assert the invariants."""
    system, _ = build_prompt(ESSAY, TAXONOMY)
    assert "put the single most relevant first" in system
    assert "Use only the phase ids listed above." in system
    assert 'No filler like "This essay..."' in system
    assert system.count("Rules:") == 1


# ── schema and validation ─────────────────────────────────────────────


def test_schema_enumerates_known_phase_ids_only() -> None:
    schema = response_schema(TAXONOMY)
    assert schema["properties"]["phases"]["items"]["enum"] == ["ideas", "any"]
    assert schema["properties"]["phases"]["minItems"] == 1
    assert schema["required"] == ["phases", "why"]
    assert schema["additionalProperties"] is False


def test_validate_rejects_unknown_ids_and_names_them() -> None:
    """Silently dropping an invented id hides a broken prompt.

    Rejecting it also produces the message a repair retry feeds back, so the
    model is told which id was wrong rather than asked to guess.
    """
    with pytest.raises(InvalidResponseError, match="invented"):
        validate_result({"phases": ["ideas", "invented"], "why": "ok"}, TAXONOMY)


def test_validate_rejection_message_lists_the_allowed_ids() -> None:
    with pytest.raises(InvalidResponseError) as excinfo:
        validate_result({"phases": ["invented"], "why": "ok"}, TAXONOMY)
    message = str(excinfo.value)
    assert "ideas" in message and "any" in message


def test_validate_dedupes_preserving_order() -> None:
    """Order carries meaning: the reader's chips key off the first entry."""
    result = validate_result({"phases": ["any", "ideas", "any"], "why": "ok"}, TAXONOMY)
    assert result["phases"] == ["any", "ideas"]


def test_validate_collapses_whitespace_in_why() -> None:
    result = validate_result({"phases": ["ideas"], "why": "  two\n\nwords  "}, TAXONOMY)
    assert result["why"] == "two words"


def test_validate_rejects_no_valid_phases() -> None:
    with pytest.raises(InvalidResponseError, match="no phases returned"):
        validate_result({"phases": [], "why": "ok"}, TAXONOMY)


def test_validate_rejects_empty_why() -> None:
    with pytest.raises(InvalidResponseError, match="empty `why`"):
        validate_result({"phases": ["ideas"], "why": "   "}, TAXONOMY)


def test_validate_tolerates_wrong_types() -> None:
    with pytest.raises(InvalidResponseError):
        validate_result("not a dict", TAXONOMY)
    with pytest.raises(InvalidResponseError):
        validate_result({"phases": "ideas", "why": "ok"}, TAXONOMY)


# ── cache file handling ───────────────────────────────────────────────


def test_load_existing_returns_empty_when_absent(tmp_path: Path) -> None:
    assert load_existing(tmp_path / "nope.json") == {}


def test_load_existing_returns_empty_on_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "phases.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_existing(path) == {}


def test_load_existing_returns_empty_when_key_missing(tmp_path: Path) -> None:
    path = tmp_path / "phases.json"
    path.write_text('{"other": 1}', encoding="utf-8")
    assert load_existing(path) == {}


def test_write_phases_uses_the_documented_key_order(tmp_path: Path) -> None:
    path = tmp_path / "phases.json"
    write_phases(
        path,
        {
            "essays": {},
            "generated": "2026-01-01T00:00:00Z",
            "model": "m",
            "taxonomyVersion": 1,
        },
    )
    assert list(json.loads(path.read_text(encoding="utf-8"))) == [
        "taxonomyVersion",
        "model",
        "generated",
        "essays",
    ]


def test_write_phases_matches_committed_formatting() -> None:
    """Same 2-space indent and no escaped unicode as the TypeScript writer."""
    committed = (settings.data_dir / "phases.json").read_text(encoding="utf-8")
    assert committed.startswith("{\n  ")
    assert '\n  "taxonomyVersion"' in committed


# ── the run, with the model stubbed out ───────────────────────────────


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    (tmp_path / "essays").mkdir()
    (tmp_path / "taxonomy.json").write_text(json.dumps(TAXONOMY), encoding="utf-8")
    for slug in ("a", "b"):
        # `title` mirrors `slug` so the stubbed model can identify which essay it
        # was handed by reading the prompt. Orchestration is under test here, not
        # prompt formatting.
        (tmp_path / "essays" / f"{slug}.json").write_text(
            json.dumps({**ESSAY, "slug": slug, "title": slug}), encoding="utf-8"
        )
    return tmp_path


def stub_model(monkeypatch: pytest.MonkeyPatch, *, fail_on: set[str] | None = None) -> list[str]:
    """Replace the network call, recording which slugs were classified."""
    calls: list[str] = []

    async def fake_chat_json(self: Any, *, user: str, **kwargs: Any) -> dict[str, Any]:
        # The fixture sets title == slug, so the title identifies the essay.
        slug = user.removeprefix("Title: ").split("\n")[0]
        calls.append(slug)
        if fail_on and slug in fail_on:
            raise RuntimeError("model exploded")
        return {"phases": ["ideas"], "why": f"why {slug}"}

    monkeypatch.setattr("llm.classify.OpenRouterClient.chat_json", fake_chat_json)
    monkeypatch.setattr("llm.classify.OpenRouterClient.configured", property(lambda self: True))
    return calls


async def test_classify_writes_results_for_every_essay(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_model(monkeypatch)
    stats = await classify_essays(corpus)

    assert stats.classified == 2
    payload = json.loads((corpus / "phases.json").read_text(encoding="utf-8"))
    assert set(payload["essays"]) == {"a", "b"}
    assert payload["essays"]["a"]["phases"] == ["ideas"]
    assert payload["taxonomyVersion"] == 1


async def test_second_run_is_free(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_model(monkeypatch)
    await classify_essays(corpus)
    calls = stub_model(monkeypatch)
    stats = await classify_essays(corpus)

    assert calls == [], "a cached run must make no model calls"
    assert stats.cached == 2
    assert stats.classified == 0


async def test_force_reclassifies_everything(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_model(monkeypatch)
    await classify_essays(corpus)
    calls = stub_model(monkeypatch)
    stats = await classify_essays(corpus, force=True)

    assert sorted(calls) == ["a", "b"]
    assert stats.classified == 2


async def test_edited_essay_is_reclassified(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_model(monkeypatch)
    await classify_essays(corpus)

    (corpus / "essays" / "a.json").write_text(
        json.dumps({**ESSAY, "slug": "a", "title": "a", "paragraphs": ["Rewritten."]}),
        encoding="utf-8",
    )
    calls = stub_model(monkeypatch)
    await classify_essays(corpus)

    assert calls == ["a"], "only the edited essay should be re-sent"


async def test_dry_run_makes_no_calls_or_writes(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = stub_model(monkeypatch)
    stats = await classify_essays(corpus, dry_run=True)

    assert calls == []
    assert stats.attempted == 2
    assert not (corpus / "phases.json").exists()


async def test_limit_caps_the_batch(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = stub_model(monkeypatch)
    await classify_essays(corpus, limit=1)
    assert len(calls) == 1


async def test_one_failure_does_not_lose_the_others(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of bounded fan-out: 232 successes survive one failure."""
    stub_model(monkeypatch, fail_on={"a"})
    stats = await classify_essays(corpus)

    assert len(stats.failures) == 1
    assert "a:" in stats.failures[0]
    assert stats.classified == 1
    payload = json.loads((corpus / "phases.json").read_text(encoding="utf-8"))
    assert "b" in payload["essays"]


async def test_stale_slugs_are_pruned(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tags for deleted essays must not linger in the file."""
    write_phases(
        corpus / "phases.json",
        {
            "taxonomyVersion": 1,
            "model": "m",
            "generated": "x",
            "essays": {"ghost": {"phases": ["ideas"], "why": "gone", "hash": "0"}},
        },
    )
    stub_model(monkeypatch)
    await classify_essays(corpus)

    payload = json.loads((corpus / "phases.json").read_text(encoding="utf-8"))
    assert "ghost" not in payload["essays"]


async def test_missing_taxonomy_is_a_validation_error(tmp_path: Path) -> None:
    (tmp_path / "essays").mkdir()
    with pytest.raises(ValidationError, match=r"taxonomy\.json"):
        await classify_essays(tmp_path)


async def test_missing_api_key_refuses_before_calling(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("llm.classify.OpenRouterClient.configured", property(lambda self: False))
    with pytest.raises(ValidationError, match="OPENROUTER_API_KEY"):
        await classify_essays(corpus)
