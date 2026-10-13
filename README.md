# askgraham

A fast, distraction-free reader for all 233 of Paul Graham's essays — rebuilt as a
production-grade RAG application.

**Status:** migration in progress. See [z-PLAN.md](z-PLAN.md) for the roadmap.
Phases 1–7 are complete: the corpus, hybrid retrieval, cited chat, and a measured
eval harness. Design decisions are recorded in [`docs/adr/`](docs/adr/).

## Layout

```
askgraham/
├── backend/     FastAPI + Python — corpus, retrieval, evals
├── frontend/    Next.js 16 — the reader UI
├── data/        233 essays + derived metadata (git-committed)
└── docs/        architecture and design decisions
```

## Quick start

Everything — Postgres+pgvector, the API, and the frontend — starts with one command:

```bash
docker compose up
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Postgres | `localhost:5433` (`askgraham` / `askgraham`) |

The frontend proxies `/api/*` to the backend, so the browser only ever talks to one
origin and CORS never enters the picture.

The ⌘K palette is served by `GET /api/v1/search`, so build the retrieval index once
after ingesting:

```bash
cd backend && uv run python cli.py index
```

Chat lives at `/chat` and streams from `POST /api/v1/chat`. It needs
`OPENROUTER_API_KEY`; inside the container stack set it in `backend/.env` (the
api service mounts `backend/`, not the repo root).

Two compose files:

| File | Use |
|---|---|
| `docker-compose.yml` | local dev — bind-mounted source, both services hot-reload |
| `docker-compose.prod.yml` | production — no mounts, no `--reload`, standalone frontend |

## Working on it

`docker compose up` runs in development mode: the API hot-reloads on save and the
frontend recompiles as you edit. **No `--build`, ever** — source is bind-mounted.

Migrations apply when the container starts, not on reload. After adding one:

```bash
docker compose restart api
```

Dependency changes need more than a restart. `node_modules` and `.venv` are
named volumes, so a rebuilt image does not replace their contents:

```bash
docker compose down
docker volume rm askgraham_api_venv askgraham_web_node_modules
docker compose up
```

Dev runs `next dev` against the full `node_modules`, while production runs
`next build` and the standalone server. Before shipping, check the real build:

```bash
docker compose -f docker-compose.prod.yml up --build   # production-shaped, exact
```

### Running natively instead

Faster if Turbopack feels sluggish through a bind mount, and useful for the
tooling below. Only Postgres needs to be a container:

```bash
docker compose up -d db                  # just Postgres
cd frontend && pnpm install && pnpm dev  # http://localhost:3000
cd backend && uv sync
uv run uvicorn main:app --reload         # hot reload, http://localhost:8000
```

### Checks

Backend:

```bash
cd backend
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

Frontend:

```bash
cd frontend
pnpm build
pnpm lint
```

Data pipeline. All of it lives in the backend now; `data/` has one writer.

```bash
cd backend
uv run python cli.py scrape            # paulgraham.com -> data/   (1.5s between requests)
uv run python cli.py scrape --slugs=say,fix     # a few, for spot checks
uv run python cli.py ingest            # data/ -> Postgres
uv run python cli.py classify          # LLM stage tags            (needs OPENROUTER_API_KEY)
uv run python cli.py paths             # LLM reading paths         (needs OPENROUTER_API_KEY)
uv run python cli.py index             # chunk + embed             (local ONNX, no API key)
uv run python cli.py snapshot          # Postgres -> frontend/snapshot/
uv run python cli.py export            # Postgres -> frontend/public/export/
uv run python cli.py eval              # retrieval metrics vs the gold dataset (free)
uv run python cli.py eval --answers    # + generate and judge answers    (needs OPENROUTER_API_KEY)
```

### Evals

`eval` runs 40 hand-authored questions from [`eval/datasets/qa.jsonl`](backend/eval/datasets/qa.jsonl)
through the retrieval variants and reports recall@k, MRR and nDCG@k — at the
essay level, plus paragraph coverage against the hand-labelled gold paragraphs.
It sweeps the ablations (reranker on/off, vector-only, lexical-only) in one pass,
so the report's before/after table prices the heuristics that Phases 5–6 shipped
unmeasured. Retrieval needs only Postgres and the local ONNX models, so it is
free and key-less; `--answers` adds LLM-as-judge faithfulness, relevance and
citation correctness, plus exact quote-grounding and citation-precision checks.
Every run is reproducible: temperature 0, a fixed seed, and the models, cutoff
and git revision recorded in the report.

The committed baseline is [`eval/results/baseline.md`](backend/eval/results/baseline.md);
the design is [ADR 0004](docs/adr/0004-evals.md).

`classify` and `paths` are cached on content, so a re-run only pays for essays or
path specs that actually changed. Both accept `--dry-run` to see what would run
without spending anything, and `--force` to ignore the cache.

`index` is idempotent the same way: it re-embeds only chunks whose text changed,
and re-embeds everything if the embedding model or chunk settings change. The
embedding and reranker models are local ONNX (`fastembed`) — free, offline, no
API key — and are downloaded to the model cache on first use.

A full scrape is ~233 requests and takes about six minutes. It is only needed
when Paul Graham publishes something new; the corpus is committed.

The frontend has no build scripts of its own. It renders from the committed
`frontend/snapshot/`, and search calls the backend. There is no client-side
index to build, and so no generated shard churn in git.

## Credits

All essays are © Paul Graham. This is an independent reading tool that links back
to the originals.