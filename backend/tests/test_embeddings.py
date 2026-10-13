"""Embedding helpers that do not require the model to be loaded.

The ONNX models are exercised against the real database in the integration
check; keeping them out of the unit suite keeps it fast and offline.
"""

from rag.embeddings import Embedder, Reranker, vector_literal


def test_vector_literal_renders_pgvector_syntax() -> None:
    assert vector_literal([0.1, -0.25, 3.0]) == "[0.1,-0.25,3.0]"


def test_vector_literal_handles_integers() -> None:
    assert vector_literal([1, 2]) == "[1.0,2.0]"


def test_vector_literal_is_empty_for_no_dimensions() -> None:
    assert vector_literal([]) == "[]"


def test_embedder_does_not_load_the_model_until_used() -> None:
    """Construction must stay cheap; `main` imports this module at startup."""
    assert Embedder(model_name="nope/not-real")._model is None


def test_reranker_does_not_load_the_model_until_used() -> None:
    assert Reranker(model_name="nope/not-real")._model is None
