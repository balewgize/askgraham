# 0001 — Backend module layout

- **Status:** Accepted
- **Date:** 2026-10-13
- **Phase:** 2 (Backend foundation)

## Context

The original plan put every Python module directly in `backend/`. With Phase 2
finished that was 6 files; Phases 3–7 add `schemas`, `api`, `cli`, `ingest`,
`snapshot`, `chunking`, `embeddings`, `retrieval`, `generation`, `summarization`
and `llm` — 17 `.py` files in one flat directory.

The plan deliberately chose a flat, non-packaged layout: `[tool.uv] package = false`
with `backend/` as the working root for both uvicorn and alembic. That constraint
is what makes the whole decision delicate — the usual advice ("adopt `src/` layout,
make it a real package") would have contradicted a choice already made for good
reasons.

The question was whether to introduce folders without giving that up.

## Decision

`backend/` keeps exactly three top-level modules — `main`, `config`, `cli` — and
gains four packages:

```
backend/
├── main.py          uvicorn entrypoint
├── config.py        settings + path constants
├── cli.py           batch commands
├── core/            db · models · logging_config · errors
├── rag/             ingest · chunking · embeddings · retrieval · snapshot
├── llm/             llm · generation · summarization
└── eval/            runner · metrics · judges
```

Dependencies flow one way only:

```
main · cli  →  rag · llm  →  core  →  config
```

`core/__init__.py` states this rule where a reader will actually see it.

### Why `config.py` stays at the root

It computes its own location:

```python
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
```

Every corpus path in the app — `settings.data_dir`, `env_file`, the Alembic
working directory — is derived from that constant. Moving the file into a package
does not raise an error; it silently shifts `BACKEND_DIR` down one level and
points the service at a directory that does not exist. `tests/test_config.py`
guards this, but a path constant that fails by being wrong rather than by being
absent is worth keeping where the arithmetic is obvious.

### Why `llm/` is separate from `rag/`

Embeddings are local ONNX: free, offline, reproducible, and their failure mode is
a missing model file. Everything in `llm/` talks to a remote API: it costs money
per call, needs network, and fails with rate limits and timeouts. The split makes
the cost and failure boundary visible in the directory tree instead of only in
import graphs. The plan had already drawn this line for the modules themselves;
this encodes it structurally.

### Why every package has an `__init__.py`

PEP 420 namespace packages would have worked at runtime, and were the first
design tried. They fail `mypy --strict`, which resolves `core/models.py` as both
`models` and `core.models` and aborts before typechecking anything:

```
error: Source file found twice under different module names
```

Real `__init__.py` files fix it and match the convention `tests/` already used.
Each one carries a docstring rather than re-exports — re-exporting from
`__init__.py` is the usual source of circular imports and buys nothing here.

## Consequences

- `pyproject.toml` sets `known-first-party`. It was `[]`, which caused isort to
  treat `config` and friends as third-party packages and sort them in with
  `fastapi` and `sqlalchemy`. That was a latent bug independent of this change.
- No infrastructure moved. The Dockerfile still runs `uvicorn main:app`, the
  Makefile is unchanged, `alembic.ini` keeps `prepend_sys_path = .`.
- Imports were cheap to rewrite *now* — 7 lines, because `api`, `cli` and the
  whole `rag`/`llm` surface did not exist yet. After Phase 3 the same move would
  have been a cross-cutting refactor.
- `tests/test_health.py` monkeypatches the string `"core.db.get_sessionmaker"`.
  String targets do not show up in a search for `import`, and a missed one makes
  the test pass while asserting nothing.

## Alternatives rejected

| Option | Why not |
|---|---|
| `src/` layout, make it a real package | Contradicts the non-packaged decision; a larger change than the problem needed |
| Namespace packages, no `__init__.py` | Breaks `mypy --strict` (above) |
| Move `config.py` into `core/` | Silently corrupts `BACKEND_DIR` / `REPO_ROOT` |
| Keep flat, reorganize in Phase 7 | The cost of moving grows every phase; doing it now cost 7 lines |