"use client";

import Link from "next/link";
import { useMemo } from "react";
import type { ResolvedPath } from "@/lib/paths";
import Disclosure from "./disclosure";
import { usePathDone } from "./reader-prefs";

/** "12 essays · 3h 40m" — total reading time for a path. */
function summarize(steps: ResolvedPath["steps"]): string {
  const minutes = steps.reduce((sum, s) => sum + s.reading_time_min, 0);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const time = hours > 0 ? `${hours}h${rest > 0 ? ` ${rest}m` : ""}` : `${rest}m`;
  return `${steps.length} essays · ${time}`;
}

function PathCard({ path }: { path: ResolvedPath }) {
  const done = usePathDone(path.id);
  const doneSet = useMemo(() => new Set(done), [done]);

  const total = path.steps.length;
  const complete = doneSet.size >= total;
  // Resume beats "Start" — one tap back into the next unfinished essay.
  const nextUp = path.steps.find((s) => !doneSet.has(s.slug));
  const cta = complete ? "Review path" : doneSet.size === 0 ? "Begin" : "Continue";
  const pct = total > 0 ? Math.round((doneSet.size / total) * 100) : 0;

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-line bg-raised p-4 transition-colors hover:border-line-firm">
      <div>
        <div className="flex items-baseline justify-between gap-2">
          <p className="truncate text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-subtle">
            {path.audience}
          </p>
          <p className="shrink-0 text-[11px] tabular-nums text-fg-subtle">{summarize(path.steps)}</p>
        </div>
        <h2 className="mt-1.5 font-serif text-lg font-semibold leading-snug tracking-tight text-fg">
          {path.title}
        </h2>
        <p className="mt-1 text-[13px] leading-snug text-fg-muted">{path.subtitle}</p>
      </div>

      <div>
        <div className="flex items-center justify-between gap-3">
          <Link
            href={nextUp ? `/essays/${nextUp.slug}` : `/paths/${path.id}`}
            className="inline-flex min-h-8 items-center gap-1.5 rounded-lg bg-fg px-3.5 text-[13px] font-medium text-surface transition-opacity hover:opacity-85"
          >
            {cta}
            <span aria-hidden="true">→</span>
            <span className="sr-only">
              {complete ? path.title : `${path.title}: ${nextUp?.title}`}
            </span>
          </Link>
          <Link
            href={`/paths/${path.id}`}
            className="text-[13px] text-fg-muted underline decoration-line underline-offset-4 transition-colors hover:text-fg"
          >
            See all {total}
          </Link>
        </div>

        <div className="mt-3 flex items-center gap-2.5">
          <div
            className="h-0.5 flex-1 overflow-hidden rounded-full bg-fg/10"
            role="progressbar"
            aria-valuenow={doneSet.size}
            aria-valuemin={0}
            aria-valuemax={total}
            aria-label={`${path.title} progress`}
          >
            <div
              className="h-full rounded-full bg-accent transition-[width] duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="shrink-0 text-[11px] tabular-nums text-fg-subtle">
            {complete ? "All read" : `${doneSet.size}/${total}`}
          </span>
        </div>
      </div>
    </li>
  );
}

/** Guided entry points above the catalog. One card per curated reading path. */
export default function StartHere({ paths }: { paths: ResolvedPath[] }) {
  if (paths.length === 0) return null;

  return (
    <Disclosure
      className="mb-6"
      label="Start here"
      meta={`${paths.length} guided ${paths.length === 1 ? "path" : "paths"}`}
    >
      <ul className="grid gap-3 sm:grid-cols-2">
        {paths.map((p) => (
          <PathCard key={p.id} path={p} />
        ))}
      </ul>
    </Disclosure>
  );
}