# askgraham

A fast, distraction-free reader for all 233 of Paul Graham's essays — rebuilt as a
production-grade RAG application.

**Status:** migration in progress. See [z-PLAN.md](z-PLAN.md) for the roadmap.

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
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Postgres | `localhost:5433` (`askgraham` / `askgraham`) |

The frontend proxies `/api/*` to the backend, so the browser only ever talks to one
origin and CORS never enters the picture.

## Working on it

For fast iteration, run the backend natively against the compose database:

```bash
docker compose up -d db                       # just Postgres
cd backend && uv sync
uv run uvicorn main:app --reload              # hot reload
```

Backend checks:

```bash
cd backend
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

Frontend checks:

```bash
cd frontend
pnpm install
pnpm build
pnpm lint
```

Data pipeline (LLM scripts need `OPENROUTER_API_KEY`), run from `frontend/`:

```bash
pnpm scrape         # re-scrape essays -> data/
pnpm classify       # LLM stage tags
pnpm paths          # LLM reading paths
pnpm export:corpus  # regenerate downloadable bundles
```

## Credits

All essays are © Paul Graham. This is an independent reading tool that links back
to the originals.