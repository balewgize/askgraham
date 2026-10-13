import path from "node:path";
import type { NextConfig } from "next";

/**
 * Base URL the Next.js server uses to reach the FastAPI backend for the
 * server-side `/api/*` proxy (search, and chat from Phase 6).
 *
 * Defaults to a locally running API so `pnpm dev` works without Docker.
 * Inside docker-compose it is overridden with the service name (`api`).
 */
const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Emits .next/standalone with only the runtime files, which keeps the
  // production image small.
  output: "standalone",

  // This app lives at `frontend/` inside a monorepo, so tracing must start at
  // the repo root — otherwise files above `frontend/` are dropped from the
  // standalone bundle.
  outputFileTracingRoot: path.join(__dirname, ".."),

  // `snapshot/` is read at build time and baked into the prerendered HTML, so
  // it is not needed at runtime and tracing it would add ~4MB of JSON to the
  // image. The frontend never reads `data/`; the pipeline lives in `backend/`.
  outputFileTracingExcludes: {
    "/*": ["../snapshot/**/*"],
  },

  // Proxy `/api/*` to the backend so the browser only ever talks to one origin.
  // Avoids CORS entirely and matches a single-domain production deployment.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiBaseUrl}/api/:path*` },
    ];
  },
};

export default nextConfig;