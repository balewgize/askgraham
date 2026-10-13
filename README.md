# askgraham

A fast, distraction-free reader for all 233 of Paul Graham's essays.

## Layout

```
askgraham/
├── backend/     FastAPI + Python — corpus, retrieval, evals (in progress)
├── frontend/    Next.js 16 — the reader UI
├── data/        233 essays + derived metadata (git-committed)
└── docs/        architecture and design decisions
```

## Quick start

```bash
cd frontend
pnpm install
pnpm dev
```

Runs on http://localhost:3000. The reader works immediately from committed data —
no backend or API key required.

## Scripts

```bash
pnpm build           # production build
pnpm lint            # eslint

pnpm scrape          # re-scrape essays -> ../data/
pnpm classify        # LLM stage tags (needs OPENROUTER_API_KEY)
pnpm paths           # LLM reading paths (needs OPENROUTER_API_KEY)
pnpm export:corpus   # regenerate downloadable bundles
```

## Credits

All essays are © Paul Graham. This is an independent reading tool that links back
to the originals.