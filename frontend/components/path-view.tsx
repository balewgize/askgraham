"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import type { ResolvedPath } from "@/lib/paths";
import { setActivePath, usePathDone } from "./reader-prefs";

export default function PathView({ path }: { path: ResolvedPath }) {
  const done = usePathDone(path.id);

  useEffect(() => {
    setActivePath(path.id);
  }, [path.id]);

  const doneSet = useMemo(() => new Set(done), [done]);
  const firstIncomplete = path.steps.find((s) => !doneSet.has(s.slug));
  const complete = doneSet.size >= path.steps.length;

  return (
    <div>
      <Link
        href="/"
        className="mb-5 inline-flex min-h-9 items-center gap-1.5 text-sm text-fg-muted transition-colors hover:text-fg"
      >
        <span aria-hidden="true">←</span> All essays
      </Link>
      <header className="mb-7 max-w-[46ch]">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-subtle">Reading path</p>
        <h1 className="mt-1.5 font-serif text-3xl font-semibold tracking-tight">{path.title}</h1>
        <p className="mt-2 text-sm text-fg-subtle">{path.subtitle}</p>
        <p className="mt-3 text-[0.95rem] leading-relaxed text-fg-muted">{path.description}</p>

        <div className="mt-5">
          <div
            className="h-1.5 w-full overflow-hidden rounded-full bg-fg/10"
            role="progressbar"
            aria-valuenow={doneSet.size}
            aria-valuemin={0}
            aria-valuemax={path.steps.length}
            aria-label={`${path.title} progress`}
          >
            <div
              className="h-full rounded-full bg-accent transition-[width] duration-300"
              style={{ width: `${Math.round((doneSet.size / path.steps.length) * 100)}%` }}
            />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            {complete ? (
              <span className="text-sm font-medium text-accent">Path complete.</span>
            ) : (
              <Link
                href={`/essays/${firstIncomplete!.slug}`}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-fg px-4 text-sm font-medium text-surface transition-opacity hover:opacity-85"
              >
                {doneSet.size === 0 ? "Start path" : "Continue"}
                <span aria-hidden="true">→</span>
              </Link>
            )}
            <span className="text-xs tabular-nums text-fg-subtle">
              {doneSet.size} of {path.steps.length} read
            </span>
          </div>
        </div>
      </header>

      <ol className="space-y-0.5">
        {path.steps.map((step, i) => {
          const isDone = doneSet.has(step.slug);
          return (
            <li key={step.slug}>
              <Link
                href={`/essays/${step.slug}`}
                className="flex items-start gap-3 rounded-lg border border-transparent px-3 py-3 transition-colors hover:border-line hover:bg-fg/[0.04]"
              >
                <span
                  role="img"
                  aria-label={isDone ? "Read" : "Not read"}
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] ${
                    isDone ? "border-accent bg-accent text-accent-fg" : "border-line-firm text-transparent"
                  }`}
                >
                  ✓
                </span>
                <span className="w-5 shrink-0 pt-0.5 text-right text-xs tabular-nums text-fg-subtle">{i + 1}.</span>
                <div className="min-w-0 flex-1">
                  <span className={`font-medium leading-snug ${isDone ? "text-fg-subtle" : "text-fg"}`}>
                    {step.title}
                  </span>
                  <span className="ml-2 shrink-0 text-xs tabular-nums text-fg-subtle">{step.reading_time_min} min</span>
                  {step.note && <span className="mt-0.5 block text-sm leading-relaxed text-fg-muted">{step.note}</span>}
                </div>
              </Link>
            </li>
          );
        })}
      </ol>

      <p className="mt-10 border-t border-line pt-4 text-xs text-fg-subtle">
        Curated automatically from the full catalog, like the stage tags. Feedback welcome.
      </p>
    </div>
  );
}