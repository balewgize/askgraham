# 0002 — Hybrid retrieval and the search index

- **Status:** Accepted
- **Date:** 2026-10-13
- **Phase:** 5 (Chunking, embeddings, hybrid retrieval)

## Context

Phase 5 adds retrieval. The plan committed to Postgres + pgvector, local ONNX
embeddings, and "RRF fusion of both, then optional reranker". It left open how
chunks are stored, how lexical search is indexed, and — because the frontend
already had a working ⌘K palette — whether search stays client-side.

That last question mattered more than it looked. The palette ran on a
build-time FlexSearch index committed to `frontend/public/search-index/`. One
shard, `body.1.map.json`, is ~2MB and re-exports in a different byte order on
every run, so every build produced an uncommitted diff. Removing it also
removed the last TypeScript build scripts, which meant porting the corpus
export too.

## Decision

Retrieval is server-side, in three modules under `rag/`:

```
rag/chunking.py     paragraphs -> token-budgeted chunks (paragraph-aware)
rag/embeddings.py   fastembed: bge-small-en-v1.5 + a cross-encoder reranker
rag/retrieval.py    index_chunks + hybrid_search (pgvector + FTS, RRF)
```

One `chunks` table carries everything the two first-stage retrievals need:

```sql
embedding  vector(384)                                  -- pgvector, HNSW
tsv        tsvector GENERATED ALWAYS AS
           (to_tsvector('english', text)) STORED        -- GIN
```

`GET /api/v1/search` runs three first-stage arms — dense, body-lexical and
title-lexical — fuses them with weighted Reciprocal Rank Fusion, then reranks
the fused head with a cross-encoder. The frontend palette calls it and no
longer ships an index. `frontend/scripts/` is deleted; the export that used to
live there is now `rag/export.py` + `uv run python cli.py export`.

### Why server-side search

The client index could only match words, had to be shipped to every visitor,
and churned in git. Moving it to the backend is what makes hybrid retrieval
possible at all: the dense arm needs the vectors, and the lexical arm needs
Postgres. It also means one ranking implementation serves the palette, the chat
in Phase 6, and the evals in Phase 7 — instead of a client approximation that
can silently disagree with the measured one.

### Why RRF, not score normalization

Cosine distance and `ts_rank_cd` are not on the same scale, and any fixed
normalization is a guess that has to be re-tuned whenever either changes.
Reciprocal Rank Fusion uses only the *ranks*: `Σ w_i/(k + rank)`. It is a few
lines, has one constant (`k=60`, the paper's default), and a document that
ranks respectably in both arms beats one that wins a single arm. Phase 8 sweeps
`k` and the weights rather than hand-tuning score normalizations.

### Why the title is a separate, boosted arm

The first cut indexed only body text, and the palette got worse for exactly the
queries the old client index was good at. "do things" did not return "Do Things
that Don't Scale": the essay barely uses the phrase in prose, dense retrieval
cannot resolve a three-word generic query, and the chunk `tsvector` had no
title. The palette's best trick had been matching the *title*, and the server
had quietly dropped it.

So the title is scored as its own field and fused as a third arm, over the
essay's opening chunk (the snippet a title match should cite). Two details make
it behave:

- **The `simple` dictionary, not `english`.** Stemming and stopword removal
  help long prose and hurt short titles. With `english`, "do things" reduces to
  `'thing'` and matches "Is There Such a Thing as Good Taste?" as strongly as the
  essay actually called "Do Things…". With `simple` the query is `'do' &
  'things'`, and only the real title satisfies it.
- **A weight of 3.** A title is short and intentional; matching it is stronger
  evidence than matching one body chunk. Without the boost, one title rank still
  lost to documents that hit two other arms. This is the BM25F field-boost idea,
  expressed in RRF weights.

The knobs are `TITLE_BOOST` and `RRF_K`, both settings, so Phase 8 can measure
them like everything else.

### Why a generated `tsvector`

A generated column means Postgres derives the lexical index from `text`; no
Python path can forget to update it, and it cannot drift from the content it
indexes. The alternative — a trigger or an application-side write — is one more
thing that can be wrong in exactly the case that matters (a re-index).

### Why chunk hashes *and* a model signature

`index` re-embeds only chunks whose `content_hash` changed, which is the
expensive path. But a hash match is only meaningful if the vectors came from
the same model. So `generation_meta` stores the model name and the chunking
parameters under the `chunks` artifact, and any change there invalidates the
whole index. Without that, swapping to `bge-base` in Phase 8 would silently
mix 384- and 768-dimensional vectors.

### Why chunks live below the model limit

`chunk_max_tokens = 384` against the model's 512-token truncation. The margin
absorbs sub-word merges at join boundaries, where the tokens of a joined chunk
can exceed the sum of its parts. A chunk that is silently truncated embeds as
something the user never wrote, and the citation still looks correct.

### Why the reranker is optional

A cross-encoder is far more accurate than the bi-encoder and far more
expensive. It is a config flag (`RERANK_ENABLED`) precisely so Phase 8 can
measure what it buys; RRF order is a valid, cheaper answer.

The ⌘K palette passes `rerank=false` explicitly: it fires on every debounced
keystroke, the two first-stage arms return in ~30ms combined, and the
cross-encoder turns that into seconds on a CPU box. RRF is good enough to pick
eight essays; the reranker stays on for chat and the evals, where a second of
latency is not the difference between typing and not typing. `RERANK_CANDIDATES`
bounds the cost independently of the requested result count.

## Consequences

- **The backend base image changed from Alpine to Debian slim.** `onnxruntime`
  ships only manylinux wheels, so `uv sync` cannot resolve it on musl. This is
  the one place Phase 5 reached outside `rag/`.
- **The index is a build step, not a service.** `cli.py index` is idempotent
  and safe to re-run; search assumes it has been run and returns an empty list
  rather than erroring when it has not.
- **`embedding_dim` is effectively pinned.** `Vector(384)` is in a migration.
  Swapping models to a different width is a migration plus a re-index — visible
  on purpose, rather than a runtime surprise.
- **First use downloads ~150MB.** Embedding and reranker weights are cached
  (`EMBEDDING_CACHE_DIR`, a compose volume); the download is a one-time cost,
  paid on `index` rather than on a user's first keystroke.
- **Reranking is off the event loop.** ONNX `run()` blocks, so both stages run
  in a thread; a blocking call in the request handler would stall the server.
- **The export's output is byte-identical to the TypeScript it replaces** for
  `essays.md`, which is the cheapest available proof that the port is faithful.

## Alternatives rejected

| Option | Why not |
|---|---|
| Keep FlexSearch, ignore Phase 5 search | No dense arm, no citations, per-visitor download, git churn |
| Single SQL statement doing fusion | RRF in SQL is unreadable and untestable; two queries plus a pure function is clearer at this scale |
| IVFFlat instead of HNSW | Needs a training step and a rebuild as rows change; HNSW has no such cliff |
| Add a trigger for `tsv` | A generated column is strictly simpler and cannot be skipped |
| Score normalization instead of RRF | Needs retuning whenever either arm's scale changes |
| Ship the reranker on by default with no flag | Phase 8 cannot price it without an ablation switch |
| Commit the export bundles | ~15MB of regenerated artifacts with a timestamp in every file |
