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
docker compose up
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Postgres | `localhost:5433` (`askgraham` / `askgraham`) |

The frontend proxies `/api/*` to the backend, so the browser only ever talks to one
origin and CORS never enters the picture.

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