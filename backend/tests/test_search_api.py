"""Search endpoint contract.

The live search path needs Postgres and the ONNX embedder, so it is covered by
the integration check rather than here. These tests pin the public contract —
the route exists and the snippet shaping behaves — without infrastructure.
"""

from fastapi import FastAPI

from main import _SNIPPET_CHARS, _snippet

from .conftest import served_paths


def test_search_route_is_in_the_api_contract(app: FastAPI) -> None:
    assert "/api/v1/search" in served_paths(app)


def test_chat_route_is_in_the_api_contract(app: FastAPI) -> None:
    assert "/api/v1/chat" in served_paths(app)


def test_essay_route_is_in_the_api_contract(app: FastAPI) -> None:
    assert "/api/v1/essays/{slug}" in served_paths(app)


def test_short_text_is_returned_whole() -> None:
    assert _snippet("hello   world") == "hello world"


def test_long_text_is_truncated_on_a_word_boundary() -> None:
    snippet = _snippet("word " * 200)
    # `- 1` for the ellipsis, and trimming the trailing space before it.
    assert len(snippet) <= _SNIPPET_CHARS + 1
    assert snippet.endswith("…")
    assert not snippet[:-1].endswith(" ")
