import path from "node:path";
import type { NextConfig } from "next";

/**
 * Base URL the server uses to reach the FastAPI backend.
 *
 * Inside docker-compose this is the service name (`api`). Overriding it lets a
 * build run against a deployed API, e.g. `API_BASE_URL=https://api.example.com`.
 */
const apiBaseUrl = process.env.API_BASE_URL ?? "http://api:8000";

const nextConfig: NextConfig = {
  // Emits .next/standalone with only the runtime files, which keeps the
  // production image small.
  output: "standalone",

  // This app lives at `frontend/` inside a monorepo, so tracing must start at
  // the repo root — otherwise files above `frontend/` are dropped from the
  // standalone bundle.
  outputFileTracingRoot: path.join(__dirname, ".."),

  // Every route is `force-static`, so the essay corpus is read at build time and
  // baked into the prerendered HTML. It is never touched at runtime, so tracing
  // it would only add ~4MB of JSON to the image.
  outputFileTracingExcludes: {
    "/*": ["../data/**/*"],
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