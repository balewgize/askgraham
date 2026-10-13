"""Grounded chat answers: retrieved sources in, a cited answer out.

Layering note: this module talks to the model only. Retrieval lives in `rag`
and is invoked by the API layer (`main.py`), which hands the sources in. That
keeps `rag` and `llm` siblings rather than one importing the other.

The model is given each source labelled with its citation token,
`[slug#start-end]`, and told to use those tokens inline. Because the token is
built from the chunk's own paragraph range, a citation in the answer resolves
straight back to the text that supported it — the thing that makes the answer
checkable rather than merely plausible.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import httpx

from core.logging_config import log
from llm.client import LLMError, OpenRouterClient

SYSTEM_PROMPT = (
    "You answer questions about Paul Graham's essays using only the numbered "
    "sources provided.\n"
    "\n"
    "Rules:\n"
    "- Cite the source for every claim inline, using its exact token, e.g. "
    "[do-things#0-4]. A sentence may cite more than one source.\n"
    "- Use only tokens that appear in the sources. Never invent one.\n"
    "- If the sources do not answer the question, say so plainly. Do not fill "
    "gaps from prior knowledge.\n"
    "- Be direct and specific. Prefer Graham's own framing over generic advice.\n"
    '- Write a few short paragraphs at most. No preamble like "Based on the '
    'sources".'
)


@dataclass(frozen=True)
class Source:
    """One retrieved passage, and the handle the answer cites it by."""

    slug: str
    title: str
    start_paragraph: int
    end_paragraph: int
    text: str

    @property
    def citation(self) -> str:
        return f"{self.slug}#{self.start_paragraph}-{self.end_paragraph}"


@dataclass(frozen=True)
class Turn:
    role: str
    content: str


def build_context(sources: Sequence[Source]) -> str:
    """Label each source with its citation token, then its text."""
    return "\n\n".join(f"[{s.citation}] {s.title}\n{s.text}" for s in sources)


def build_messages(
    question: str, history: Sequence[Turn], sources: Sequence[Source]
) -> list[dict[str, str]]:
    """System prompt, prior turns, then the sources and the question.

    History is included verbatim so follow-ups ("what about the second point?")
    make sense to the model. Retrieval still uses only the latest message, which
    is the known limitation: the model resolves the reference, the retriever
    does not.
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history:
        if turn.role in ("user", "assistant") and turn.content.strip():
            messages.append({"role": turn.role, "content": turn.content})
    messages.append(
        {
            "role": "user",
            "content": f"Sources:\n\n{build_context(sources)}\n\n---\nQuestion: {question}",
        }
    )
    return messages


async def stream_answer(
    *,
    question: str,
    history: Sequence[Turn],
    sources: Sequence[Source],
    client: OpenRouterClient | None = None,
    usage: dict[str, int] | None = None,
    temperature: float | None = None,
    seed: int | None = None,
) -> AsyncIterator[str]:
    """Stream a cited answer. Yields text deltas.

    `temperature` is passed straight to the provider and left unset for chat,
    where the default sampling is part of the feel. The eval sets it to 0 so an
    answer is reproducible rather than merely plausible.
    """
    openrouter = client or OpenRouterClient()
    if not openrouter.configured:
        raise LLMError("OPENROUTER_API_KEY is not set")

    messages = build_messages(question, history, sources)
    log.info("chat.generating", sources=len(sources), history=len(history))

    async with httpx.AsyncClient(follow_redirects=True) as http:
        async for delta in openrouter.stream_chat(
            messages=messages,
            client=http,
            app_title="Ask Graham chat",
            usage=usage,
            temperature=temperature,
            seed=seed,
        ):
            yield delta


__all__ = ["SYSTEM_PROMPT", "Source", "Turn", "build_context", "build_messages", "stream_answer"]
