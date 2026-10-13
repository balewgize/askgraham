# syntax=docker/dockerfile:1

# Build context is the repo root, not frontend/, because the essay corpus in
# data/ is read during `next build` to prerender all 233 pages.

# ── deps ──────────────────────────────────────────────────────────────
FROM node:22-alpine AS deps

ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

WORKDIR /repo/frontend

# Manifests only, so this layer is reused on every source-only change.
# The pnpm store is a BuildKit cache rather than a layer: it costs no image
# size and makes reinstall nearly instant.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./

RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile

# ── dev ─────────────────────────────────────────────────────────────────
# Reuses `deps`, which has full node_modules *including* devDependencies —
# the `runner` stage does not. Nothing is COPYed here: source arrives via the
# bind mounts in docker-compose.yml, so no rebuild is needed on edit.
#
# Must stay above `runner`, not below it: the last stage is the implicit
# default --target, and `runner` has to remain that.
FROM deps AS dev

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /repo/frontend

EXPOSE 3000

# `pnpm dev` (tsx scripts/export-corpus.ts && next dev) rather than bare
# `next dev`, so the container behaves exactly like the host. `next dev`
# already defaults to hostname 0.0.0.0, which is what the port map needs.
CMD ["pnpm", "dev"]

# ── builder ────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable

WORKDIR /repo/frontend

COPY --from=deps /repo/frontend/node_modules ./node_modules
COPY frontend ./

# A missing corpus here fails the build loudly rather than silently emitting
# an empty site.
COPY data /repo/data

# Next's own cache is a BuildKit cache mount: it survives between builds but
# never lands in a layer, which is where most rebuild time is saved.
RUN --mount=type=cache,id=next-cache,target=/repo/frontend/.next/cache \
    pnpm build

# ── runner ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1

# The standalone server still should not run as root.
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 --ingroup nodejs nextjs

# `output: "standalone"` produces a self-contained server with only traced
# runtime files. The corpus is excluded from the trace, so no JSON ships here.
COPY --from=builder --chown=nextjs:nodejs /repo/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/frontend/.next/static ./frontend/.next/static
COPY --from=builder --chown=nextjs:nodejs /repo/frontend/public ./frontend/public

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "require('http').get('http://127.0.0.1:3000/',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "frontend/server.js"]