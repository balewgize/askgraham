# syntax=docker/dockerfile:1

# Debian slim (glibc) rather than Alpine (musl). Alpine was the original choice
# for its size, but `onnxruntime` — pulled in by `fastembed` for local
# embeddings — publishes only manylinux wheels, so `uv sync` cannot satisfy it
# on musl. The image is a little larger; the alternative is not embedding.
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Model cache. Both fastembed and huggingface_hub read these; the compose
    # stack mounts a volume here so models survive a container restart.
    HF_HOME=/models \
    EMBEDDING_CACHE_DIR=/models \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# onnxruntime links against libgomp at runtime; Debian slim does not ship it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer first, so editing source never re-resolves packages.
# --no-cache keeps uv's download cache out of the image; it is the single
# biggest size win here.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .

# Non-root: the service only reads code, talks to Postgres, and writes models
# into the cache directory. Plain uid/gid 1001 (not `--system`) because Debian's
# system uid range stops at 999 and would warn.
RUN groupadd --gid 1001 app \
    && useradd --uid 1001 --gid app --home-dir /home/app --create-home app \
    && mkdir -p /models \
    && chown app:app /models

USER app
EXPOSE 8000

# Healthy means the API answers, not merely that the port accepts connections.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
