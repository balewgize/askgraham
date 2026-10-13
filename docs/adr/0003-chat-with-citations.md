# 0003 — Chat with citations

- **Status:** Accepted
- **Date:** 2026-10-13
- **Phase:** 6 (Chat with citations)

## Context

Phase 6 turns retrieval into a conversation: stream an answer grounded in the
corpus, with citations that resolve to a specific essay and paragraph. The
pieces exist — `hybrid_search` already returns `slug` and a paragraph range.
The open questions were where orchestration lives, how the answer streams, and
what a citation is on the wire.

## Decision

One endpoint: `POST /api/v1/chat`, server-sent events. `llm/generation.py` holds
the prompt and the streaming; `main.py` retrieves and hands the passages in.

A citation is a token, `[slug#start-end]`, and the answer carries them inline.
The model is given sources labelled with those tokens and told to cite with
them. Because the token is the chunk's own paragraph range, it resolves straight
back to the text that supported the claim.

The event stream is `sources`, then `delta` per token, then `done` (or `error`).

### Why `rag` and `llm` stay siblings

The dependency rule is `main · cli → rag · llm → core → config`; `rag` and `llm`
do not import each other. Retrieval is the API layer's job, generation is
`llm`'s, and `generation.py` takes a list of passages — it never imports
`rag.retrieval`. If `llm` imported `rag`, the cost boundary the package split
exists to draw would pass back through it.

### Why retrieval runs before the stream

The endpoint awaits `hybrid_search` and only then returns a `StreamingResponse`.
That keeps the request's database session out of the stream lifetime entirely:
the model call is the only thing streamed. It also means the `sources` event is
sent first, so the UI can show what is being read while the answer is written.

### Why the token is not retried

`stream_chat` does not retry. Once the first token is on the wire the client has
seen a partial answer; replaying would duplicate it. Repair retries make sense
for `chat_json`, where nothing is emitted until a complete object exists — not
here. A mid-stream failure becomes an `error` event.

### Why no query rewriting yet

A follow-up ("what about the second point?") is resolved by the *model*, which
sees the history, but not by the *retriever*, which sees only the latest
message. That is the known gap. Rewriting with a second LLM call would close it
at the cost of an extra round trip on every turn; that is a Phase 8 decision
made against eval numbers, not one to guess now.

## Consequences

- **Answer latency is dominated by generation**, not retrieval: ~30ms to
  retrieve, seconds to stream. The `done` event carries token usage from
  OpenRouter (`stream_options`), so cost per query is logged as it happens.
- **Rate limiting is deferred to Phase 10.** The endpoint is unauthenticated
  and spends money per call; that is acceptable locally and not in production.
- **Citations point at an essay, not yet an anchor.** The reader has no
  per-paragraph DOM id, so a citation links to `/essays/<slug>` and shows the
  paragraph range as text. Paragraph anchors are a small reader change for
  later.

## Alternatives rejected

| Option | Why not |
|---|---|
| Non-streaming JSON response | The first token arriving in ~1s is the whole reason chat feels alive |
| A `rag` import inside `llm/generation.py` | Breaks the sibling rule and the cost boundary it encodes |
| Cite with `[1]`, `[2]` and send a separate map | Numbers are meaningless out of band; a token that carries the slug survives copy-paste and logging |
| Retry the stream | Duplicate prefixes once tokens have been emitted |
| LLM query rewriting now | An extra paid call on every turn, with no eval to justify it yet |
