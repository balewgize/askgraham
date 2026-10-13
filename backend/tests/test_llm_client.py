"""LLM client behaviour.

Tested against a mock transport rather than the network, so the retry policy and
the response handling are pinned down. Both matter financially: a retry policy
that retries too little loses work, and one that retries too much costs money.
"""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from llm.client import (
    LLMError,
    OpenRouterClient,
    RetryableLLMError,
    collapse_whitespace,
    extract_json,
    map_bounded,
)

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def ok_response(content: str = '{"ok": true}') -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
        request=httpx.Request("POST", "https://example.test"),
    )


Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler,
    monkeypatch: pytest.MonkeyPatch,
    **overrides: Any,
) -> tuple[OpenRouterClient, httpx.MockTransport, list[float]]:
    """Client wired to a mock transport, with sleeps neutralised.

    Captures the sleeps so the retry backoff can be asserted instead of waited.
    """
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("llm.client.asyncio.sleep", fake_sleep)
    client = OpenRouterClient(
        api_key=overrides.pop("api_key", "test-key"),
        base_url=overrides.pop("base_url", "https://example.test"),
        **overrides,
    )
    return client, httpx.MockTransport(handler), slept


# ── extract_json ──────────────────────────────────────────────────────


def test_extract_json_plain() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_strips_markdown_fence() -> None:
    """Some models fence the JSON even when asked for json_schema."""
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_strips_bare_fence() -> None:
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_ignores_surrounding_prose() -> None:
    """A leading sentence must not break parsing."""
    assert extract_json('Sure! Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}


def test_extract_json_handles_nested_objects() -> None:
    assert extract_json('prefix {"a": {"b": [1, 2]}} suffix') == {"a": {"b": [1, 2]}}


def test_extract_json_rejects_no_object() -> None:
    with pytest.raises(LLMError, match="no JSON object"):
        extract_json("I cannot help with that.")


def test_extract_json_rejects_malformed() -> None:
    with pytest.raises(LLMError, match="malformed JSON"):
        extract_json("{not valid}")


# ── collapse_whitespace ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  a   b  ", "a b"),
        ("line\n\nbreak", "line break"),
        ("tab\tsep", "tab sep"),
        ("", ""),
    ],
)
def test_collapse_whitespace(raw: str, expected: str) -> None:
    assert collapse_whitespace(raw) == expected


# ── chat_json happy path ──────────────────────────────────────────────


async def test_chat_json_returns_parsed_object(monkeypatch: pytest.MonkeyPatch) -> None:
    client, transport, _ = make_client(lambda request: ok_response(), monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http:
        result = await client.chat_json(
            system="s", user="u", schema=SCHEMA, schema_name="x", app_title="t", client=http
        )
    assert result == {"ok": True}


async def test_chat_json_sends_a_strict_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider is asked to constrain output, not just asked politely."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return ok_response()

    client, transport, _ = make_client(handler, monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http:
        await client.chat_json(
            system="sys", user="usr", schema=SCHEMA, schema_name="nm", app_title="ttl", client=http
        )

    assert seen["model"] == client.model
    assert seen["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    fmt = seen["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "nm"
    assert fmt["json_schema"]["schema"] == SCHEMA


async def test_chat_json_sends_attribution_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return ok_response()

    client, transport, _ = make_client(handler, monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http:
        await client.chat_json(
            system="s", user="u", schema=SCHEMA, schema_name="x", app_title="My Title", client=http
        )
    assert seen["authorization"] == "Bearer test-key"
    assert seen["x-title"] == "My Title"


# ── retry policy ──────────────────────────────────────────────────────


async def test_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="slow down", request=request)
        return ok_response()

    client, transport, slept = make_client(handler, monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http:
        result = await client.chat_json(
            system="s", user="u", schema=SCHEMA, schema_name="x", app_title="t", client=http
        )
    assert result == {"ok": True}
    assert calls["n"] == 2
    assert slept == [1.5]


async def test_retries_on_500_with_growing_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down", request=request)

    client, transport, slept = make_client(handler, monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(RetryableLLMError, match="503"):
            await client.chat_json(
                system="s", user="u", schema=SCHEMA, schema_name="x", app_title="t", client=http
            )
    # 3 attempts total: two sleeps, at 1x then 2x the base delay.
    assert slept == [1.5, 3.0]


async def test_does_not_retry_on_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bad request fails identically three times; failing fast is cheaper."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad request", request=request)

    client, transport, slept = make_client(handler, monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(LLMError, match="400"):
            await client.chat_json(
                system="s", user="u", schema=SCHEMA, schema_name="x", app_title="t", client=http
            )
    assert calls["n"] == 1
    assert slept == []


async def test_retries_on_unparseable_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider answered, so a retry is more likely to help than hurt."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return ok_response(content="I refuse to answer in JSON.")
        return ok_response()

    client, transport, _ = make_client(handler, monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http:
        result = await client.chat_json(
            system="s", user="u", schema=SCHEMA, schema_name="x", app_title="t", client=http
        )
    assert result == {"ok": True}
    assert calls["n"] == 2


async def test_respects_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom", request=request)

    client, transport, _ = make_client(handler, monkeypatch, max_attempts=5)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(RetryableLLMError):
            await client.chat_json(
                system="s", user="u", schema=SCHEMA, schema_name="x", app_title="t", client=http
            )
    assert calls["n"] == 5


async def test_missing_api_key_fails_without_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return ok_response()

    client, transport, _ = make_client(handler, monkeypatch, api_key="")
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
            await client.chat_json(
                system="s", user="u", schema=SCHEMA, schema_name="x", app_title="t", client=http
            )
    assert calls["n"] == 0


async def test_unexpected_response_shape_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True}, request=request)

    client, transport, _ = make_client(handler, monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(LLMError, match="unexpected response shape"):
            await client.chat_json(
                system="s", user="u", schema=SCHEMA, schema_name="x", app_title="t", client=http
            )


async def test_null_content_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": None}}]}, request=request
        )

    client, transport, _ = make_client(handler, monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(RetryableLLMError):
            await client.chat_json(
                system="s", user="u", schema=SCHEMA, schema_name="x", app_title="t", client=http
            )


# ── map_bounded ───────────────────────────────────────────────────────


async def test_map_bounded_preserves_input_order() -> None:
    async def double(value: int) -> int:
        return value * 2

    results = await map_bounded([1, 2, 3, 4], double, concurrency=2)
    assert [r for _, r, _ in results] == [2, 4, 6, 8]


async def test_map_bounded_captures_errors_without_aborting() -> None:
    """One bad item must not lose the other 232."""

    async def flaky(value: int) -> int:
        if value == 2:
            raise ValueError("nope")
        return value

    results = await map_bounded([1, 2, 3], flaky, concurrency=2)
    errors = {item: err for item, _r, err in results if err is not None}
    assert set(errors) == {2}
    assert isinstance(errors[2], ValueError)
    assert [r for _, r, e in results if e is None] == [1, 3]


async def test_map_bounded_respects_concurrency_limit() -> None:
    in_flight = 0
    peak = 0

    async def track(_value: int) -> int:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await __import__("asyncio").sleep(0.01)
        in_flight -= 1
        return 0

    await map_bounded(list(range(12)), track, concurrency=3)
    assert peak <= 3


async def test_map_bounded_handles_empty_input() -> None:
    async def identity(value: int) -> int:
        return value

    assert await map_bounded([], identity, concurrency=4) == []
