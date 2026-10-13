# syntax=docker/dockerfile:1

# Alpine (musl) rather than slim (glibc): ~50MB base vs ~150MB. Every native
# dependency here ships cp314 musllinux wheels for both x86_64 and aarch64
# (pydantic-core, asyncpg, sqlalchemy, greenlet, uvloop), so nothing compiles
# from source at build time.
FROM python:3.14-alpine

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependency layer first, so editing source never re-resolves packages.
# --no-cache keeps uv's download cache out of the image; it is the single
# biggest size win here.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .

# Non-root: the service only reads code and talks to Postgres.
# Alpine ships busybox addgroup/adduser, not the shadow-utils groupadd/useradd.
RUN addgroup -S -g 1001 app \
    && adduser -S -u 1001 -G app -h /home/app app \
    && mkdir -p /models \
    && chown app:app /models

USER app
EXPOSE 8000

# Healthy means the API answers, not merely that the port accepts connections.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]