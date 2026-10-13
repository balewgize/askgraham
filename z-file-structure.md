askgraham/ ← repo root
│
├── backend/                               ← Python code lives directly here
│   ├── pyproject.toml                     #   [tool.uv] package = false
│   ├── uv.lock
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── alembic.ini
│   ├── alembic/{env.py, script.py.mako, versions/}
│   │
│   │   Three top-level modules. Everything else is a package; see
│   │   docs/adr/0001-backend-module-layout.md for why.
│   │
│   ├── main.py            FastAPI app factory + middleware  (uvicorn main:app)
│   ├── config.py          pydantic-settings + BACKEND_DIR / REPO_ROOT
│   ├── cli.py             ingest / index / summarize / eval
│   │
│   ├── core/              infrastructure — imports config only
│   │   ├── db.py              async engine + session dep
│   │   ├── models.py          SQLAlchemy ORM
│   │   ├── logging_config.py  structlog + request-id
│   │   └── errors.py          domain errors → HTTP
│   │
│   ├── rag/               corpus pipeline — imports core, config
│   │   ├── ingest.py         data/*.json → Postgres
│   │   ├── snapshot.py       Postgres → frontend/snapshot/*.json
│   │   ├── chunking.py       paragraph-aware chunker
│   │   ├── embeddings.py     fastembed: embed + rerank (local ONNX)
│   │   └── retrieval.py      index_chunks + hybrid_search (RRF)
│   │
│   ├── llm/               model-facing — imports core, config
│   │   ├── llm.py            Protocol + OpenRouter client
│   │   ├── generation.py     streaming chat + citations
│   │   └── summarization.py  summaries + verbatim quote check
│   │
│   ├── eval/              consumes rag + llm; neither imports it
│   │   ├── runner.py
│   │   ├── metrics.py
│   │   ├── judges.py
│   │   ├── datasets/qa.jsonl
│   │   └── results/baseline.md
│   │
│   └── tests/{__init__.py, conftest.py, test_*.py}
│
├── frontend/                              ← Next.js, unchanged for now
│   ├── app/  components/  lib/  public/  scripts/
│   ├── package.json  pnpm-lock.yaml
│   ├── next.config.ts  tsconfig.json
│   ├── postcss.config.mjs  eslint.config.mjs
│   └── AGENTS.md  CLAUDE.md
│
├── data/                                  ← 233 essays + derived metadata
│   ├── essays/*.json
│   ├── index.json  taxonomy.json
│   └── phases.json  paths.json  paths.spec.json
│
├── docs/
│   ├── architecture.md
│   └── adr/0001-backend-module-layout.md
│
├── docker-compose.yml
├── Makefile
├── pnpm-workspace.yaml
├── .gitignore  .env.example
└── README.md