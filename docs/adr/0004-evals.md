# 0004 — Evals: retrieval and answer quality

- **Status:** Accepted
- **Date:** 2026-10-13
- **Phase:** 7 (Evals harness)

## Context

Phases 5 and 6 shipped two retrieval heuristics — the boosted title arm
(`TITLE_BOOST=3`) and the cross-encoder reranker — without a number to justify
either. The plan's section 6 says why that cannot stand: tuning retrieval without
metrics means a change cannot be proven to have helped, and Phase 8 is *only*
tuning. So Phase 7 builds the ruler before anyone reaches for the dials.

The open questions were what to measure, how to score an answer, and how to keep
a run reproducible enough that "before" and "after" mean something.

## Decision

One package, `backend/eval/`, four modules, one CLI command:

```
eval/metrics.py    pure ranking math: recall@k, MRR, nDCG@k, paragraph coverage
eval/judges.py     deterministic grounding + citation checks, and LLM-as-judge
eval/runner.py     dataset, retrieval sweep, answer pass, markdown report
eval/datasets/qa.jsonl   40 hand-authored questions with gold slugs/paragraphs
eval/results/baseline.md committed output of a real run
```

`uv run python cli.py eval` measures retrieval only and costs nothing.
`--answers` adds generation and judging. It imports `rag` and `llm`; neither
imports it, so the dependency arrow still points one way.

### Why retrieval is scored at the essay level

The dataset's gold is an essay slug. Retrieval returns chunks, but the unit a
reader — and the ⌘K palette — cares about is the *essay*, so chunk hits are
collapsed to their best rank per essay before scoring. That makes recall@k
success@k for a single gold essay, which is the standard single-relevance
reading. Scoring chunks without collapsing would let three chunks of the gold
essay look like three recalls.

Paragraph refs are scored separately and more strictly, as **paragraph
coverage**: the fraction of hand-labelled gold paragraphs a retrieved chunk
actually touches. That is the only way the expensive part of the dataset — the
paragraph labels — earns its keep, and it catches the failure the essay metric
cannot: retrieving the right essay in the wrong place.

### Why deterministic checks sit next to the judge

The strongest interview answer to "how do you know the model isn't inventing
quotes?" is not "we asked another model". It is "we check each quoted span
against the source and report the rate". So quotes are checked for free and with
no room to argue. The comparison is deliberately narrow: a quote is split into
fragments on `...` elisions and on the app's own inline citation tokens, trimmed
of boundary punctuation, normalized for typography and case, and then each
fragment must appear verbatim in the retrieved sources. Those tolerances cover
formatting — typography, elision, and the citation syntax the model was told to
use — and nothing else. A reworded phrase still fails.

Citation tokens are checked separately and for an *exact* `[slug#start-end]`
match, because the range is the claim. A near miss (`ds#0-3` for `ds#0-4`) is an
invented range, not a typo to forgive. The LLM judge adds what neither substring
check can: faithfulness, relevance, and whether a citation actually supports its
sentence. Where the deterministic and judged verdicts disagree is itself a
finding.

### Why one command runs every variant

Retrieval is ~50ms and free, so `eval` sweeps the ablations in one pass and emits
the before/after table directly: hybrid with and without the reranker, and each
first-stage arm alone. This is what prices the reranker. The answer pass runs
only for the primary variant, because it is the part that costs money.

### Why temperature 0 and a seed

An eval that samples differently every run cannot be compared to itself.
Generation and judging both run at `temperature=0` with a fixed seed
(`EVAL_TEMPERATURE`, `EVAL_SEED`), and the report records the models, the seed,
the cutoff, the RRF constants and the git revision. `chat_json` and
`stream_chat` take these as optional arguments: the authoring commands send no
sampling parameters and their requests are byte-identical to before.

### Why a judge call has a hard timeout

The provider occasionally stalls mid-response on a large judge prompt, and
httpx's read timeout did not fire. `asyncio.wait_for` around each judge
(`EVAL_REQUEST_TIMEOUT_S`) turns a hang into a retry, and a second stall into a
recorded failure. An eval that hangs forever is worse than one that marks a case
and moves on, which is the same reasoning as `map_bounded` in the LLM client.

### Why missing measurements do not read as bad ones

The aggregate excludes a metric for a case only when *that* judge failed, so a
citation judge that timed out does not also drag down that case's faithfulness.
Grounding is micro-averaged over the quotes and citations that actually exist,
because an answer that quoted nothing is not evidence of a hallucinated quote.
In the per-case table a failed judge renders as `—`, never `0/5`.

### Why the answers are opt-in

Retrieval needs only Postgres and the local ONNX models. Answer judging calls a
paid API three times per answer. Keeping them behind `--answers` means the
retrieval baseline is reproducible by anyone, on a laptop, with no key — and the
report says plainly when the answer section was not run.

## Consequences

- **The dataset is the expensive artifact.** Forty questions with verified gold
  slugs and ten with paragraph refs took longer to write than the code. A wrong
  gold slug makes the metric wrong in the one direction that flatters the
  system, so `tests/test_eval_runner.py` asserts every gold slug exists in
  `data/index.json` and every paragraph index is in range.
- **The baseline already shows the reranker is nearly free of gain**: on the
  40-case set it moves MRR by +0.01. That is a real, deflating result and exactly
  what the harness exists to surface. Phase 8 can now decide whether to keep it.
- **The title boost is not yet priced.** It is a single shared setting, so
  ablating it needs a `hybrid_search` parameter that does not exist yet. Phase 8
  adds it; the baseline records the value so the diff is visible.
- **Answer numbers depend on the judge.** The judge runs on the same model as the
  generator by default (`EVAL_JUDGE_MODEL` can separate them). A stronger judge
   is the obvious upgrade once one is available.

## Alternatives rejected

| Option | Why not |
|---|---|
| LLM judge only, no deterministic checks | A judge can be talked out of a hallucination; a substring match cannot |
| Judge against LLM-generated reference answers | The reference is another model's opinion; the corpus is the ground truth |
| Score at the chunk level without collapsing | Inflates recall when one essay returns several chunks |
| Separate `eval-retrieval` / `eval-answers` commands | The table wants both in one report, and retrieval is free enough to always run |
| Run the API endpoint instead of `hybrid_search` | The endpoint adds `limit*3` dedupe and snippet shaping; the eval should measure the function the endpoint calls |
| Commit raw generated answers | Hundreds of lines of model output that age badly; the metrics and failures are the durable part |
