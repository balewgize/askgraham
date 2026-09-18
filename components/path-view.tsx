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
      <nav className="mb-6 text-xs text-zinc-500">
        <Link href="/" className="hover:underline">
          ← All essays
        </Link>
      </nav>

      <header className="mb-6 max-w-[70ch]">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-orange-600 dark:text-orange-400">
          Reading path
        </p>
        <h1 className="mt-1 font-serif text-2xl font-bold tracking-tight sm:text-3xl" style={{ fontFamily: "Georgia, serif" }}>
          {path.title}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">{path.subtitle}</p>
        <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">{path.description}</p>
        <p className="mt-2 text-xs text-zinc-500">
          {path.steps.length} essays · in order
        </p>

        <div className="mt-4">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
            <div
              className="h-full rounded-full bg-orange-500 transition-all"
              style={{ width: `${Math.round((doneSet.size / path.steps.length) * 100)}%` }}
            />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            {complete ? (
              <span className="text-sm font-medium text-orange-700 dark:text-orange-300">Path complete.</span>
            ) : (
              <Link
                href={`/essays/${firstIncomplete!.slug}`}
                className="rounded-full bg-zinc-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
              >
                {doneSet.size === 0 ? "Start path" : "Continue"} →
              </Link>
            )}
            <span className="text-xs text-zinc-500">
              {doneSet.size} of {path.steps.length} done
            </span>
          </div>
        </div>
      </header>

      <ol className="space-y-1">
        {path.steps.map((step, i) => {
          const isDone = doneSet.has(step.slug);
          return (
            <li key={step.slug} className="flex items-start gap-3 rounded-lg px-2 py-2.5 hover:bg-black/[0.03] dark:hover:bg-white/5">
              <span
                role="img"
                aria-label={isDone ? "Read" : "Not read"}
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] ${
                  isDone
                    ? "border-orange-500 bg-orange-500 text-white"
                    : "border-black/20 text-transparent dark:border-white/25"
                }`}
              >
                ✓
              </span>
              <span className="w-5 shrink-0 pt-0.5 text-right text-xs tabular-nums text-zinc-400">{i + 1}.</span>
              <div className="min-w-0 flex-1">
                <Link href={`/essays/${step.slug}`} className="block">
                  <span className={`font-medium hover:underline ${isDone ? "text-zinc-400 line-through dark:text-zinc-500" : ""}`}>
                    {step.title}
                  </span>
                  <span className="ml-2 shrink-0 text-xs text-zinc-400">{step.reading_time_min} min</span>
                  {step.note && (
                    <span className="mt-0.5 block text-sm text-zinc-500 dark:text-zinc-400">{step.note}</span>
                  )}
                </Link>
              </div>
            </li>
          );
        })}
      </ol>

      <p className="mt-10 border-t border-black/10 pt-3 text-xs text-zinc-400 dark:border-white/10">
        Curated automatically from the full catalog, like the stage tags. Feedback welcome.
      </p>
    </div>
  );
}
