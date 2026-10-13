"""Local embeddings and reranking, via fastembed's ONNX runtime.

No torch, no network at query time, no API key in the retrieval path: both
models are small ONNX graphs downloaded once and cached. That is what makes the
eval numbers in Phase 7 reproducible and the marginal cost of a search zero.

Everything here is synchronous — ONNX `run()` blocks — so the async wrappers
hand the work to a thread. Calling the sync functions directly inside a request
handler would block the event loop for the duration of the inference.

`fastembed` is imported lazily. Importing it pulls in onnxruntime and models are
expensive to construct; tests and `/healthz` must not pay for that.
"""

import asyncio
import functools
from collections.abc import Sequence
from typing import Any

from config import settings


def vector_literal(values: Sequence[float]) -> str:
    """Render a list of floats as a pgvector literal: `[0.1,0.2,...]`.

    Used with an explicit `CAST(... AS vector)` in raw SQL, which sidesteps
    registering an asyncpg codec for the `vector` type while keeping the value a
    bound parameter rather than string-formatted SQL.
    """
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


class Embedder:
    """A loaded `bge-small-en-v1.5` model (or whatever `EMBEDDING_MODEL` says)."""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        cache_dir: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.model_name = model_name or settings.embedding_model
        self.cache_dir = (
            cache_dir if cache_dir is not None else (settings.embedding_cache_dir or None)
        )
        self.batch_size = batch_size or settings.embedding_batch_size
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=self.cache_dir,
            )
        return self._model

    @property
    def dim(self) -> int:
        return int(self._load().embedding_size)

    def count_tokens(self, text: str) -> int:
        """Exact token count in the model's own tokenizer.

        This is the chunker's budget counter, so chunks are sized in the units
        the model actually sees rather than an estimate.
        """
        return int(self._load().token_count([text]))

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed passages. BGE's document side takes no instruction prefix."""
        if not texts:
            return []
        model = self._load()
        return [vec.tolist() for vec in model.passage_embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        """Embed one query. BGE has a query-side prefix, applied by fastembed."""
        model = self._load()
        vectors = list(model.query_embed(text))
        return vectors[0].tolist() if vectors else []


class Reranker:
    """A cross-encoder that scores (query, document) pairs jointly.

    This is the second stage of the pipeline: RRF fuses cheap first-stage
    recall, then the cross-encoder reorders a short candidate list. It is much
    more expensive per document than a bi-encoder, which is why it only ever
    sees the fused head.
    """

    def __init__(
        self,
        *,
        model_name: str | None = None,
        cache_dir: str | None = None,
    ) -> None:
        self.model_name = model_name or settings.rerank_model
        self.cache_dir = (
            cache_dir if cache_dir is not None else (settings.embedding_cache_dir or None)
        )
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        return [float(score) for score in self._load().rerank(query, list(documents))]


@functools.lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Process-wide embedder. Loading the ONNX graph once is the point."""
    return Embedder()


@functools.lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()


async def embed_documents_async(
    texts: Sequence[str], *, embedder: Embedder | None = None
) -> list[list[float]]:
    """`embed_documents` off the event loop."""
    model = embedder or get_embedder()
    return await asyncio.to_thread(model.embed_documents, list(texts))


async def embed_query_async(text: str, *, embedder: Embedder | None = None) -> list[float]:
    """`embed_query` off the event loop. This is on the request's latency path."""
    model = embedder or get_embedder()
    return await asyncio.to_thread(model.embed_query, text)


async def rerank_async(
    query: str, documents: Sequence[str], *, reranker: Reranker | None = None
) -> list[float]:
    model = reranker or get_reranker()
    return await asyncio.to_thread(model.rerank, query, list(documents))


__all__ = [
    "Embedder",
    "Reranker",
    "embed_documents_async",
    "embed_query_async",
    "get_embedder",
    "get_reranker",
    "rerank_async",
    "vector_literal",
]
