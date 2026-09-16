"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDateShort } from "@/lib/dates";
import type { IndexEntry } from "@/lib/essays";

type Chip = { id: string; label: string };
type EssayPhase = { phases: string[] };

function yearOf(date: string | null): string {
  if (!date) return "Undated";
  const m = date.match(/\b(19\d{2}|20\d{2})\b/);
  return m ? m[1] : "Undated";
}

export default function EssayIndex({
  entries,
  chips,
  essayPhases,
}: {
  entries: IndexEntry[];
  chips: Chip[];
  essayPhases: Record<string, EssayPhase>;
}) {
  const [active, setActive] = useState<string | null>(null);

  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of entries) {
      const primary = essayPhases[e.slug]?.phases[0];
      if (primary) m.set(primary, (m.get(primary) ?? 0) + 1);
    }
    return m;
  }, [entries, essayPhases]);

  const filtered = useMemo(
    () => (active ? entries.filter((e) => essayPhases[e.slug]?.phases[0] === active) : entries),
    [active, entries, essayPhases],
  );

  const groups = new Map<string, IndexEntry[]>();
  for (const e of filtered) {
    const y = yearOf(e.date);
    if (!groups.has(y)) groups.set(y, []);
    groups.get(y)!.push(e);
  }
  const years = [...groups.keys()].sort((a, b) => {
    if (a === "Undated") return 1;
    if (b === "Undated") return -1;
    return Number(b) - Number(a);
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-serif text-2xl font-bold tracking-tight sm:text-3xl" style={{ fontFamily: "Georgia, serif" }}>
          Paul Graham&apos;s Essays
        </h1>
        <p className="mt-1 hidden text-xs text-zinc-400 sm:block">
          Press <kbd className="rounded border border-black/10 px-1 dark:border-white/15">/</kbd> or{" "}
          <kbd className="rounded border border-black/10 px-1 dark:border-white/15">⌘K</kbd> to search ·{" "}
          <kbd className="rounded border border-black/10 px-1 dark:border-white/15">j</kbd>/
          <kbd className="rounded border border-black/10 px-1 dark:border-white/15">k</kbd> to move between essays
        </p>
      </div>

      {chips.length > 0 && (
        <div className="mb-6 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setActive(null)}
            aria-pressed={active === null}
            className={`rounded-full border px-3 py-1 text-xs ${
              active === null
                ? "border-zinc-900 bg-zinc-900 font-medium text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                : "border-black/10 text-zinc-600 hover:bg-black/5 dark:border-white/15 dark:text-zinc-300 dark:hover:bg-white/10"
            }`}
          >
            All · <span className="opacity-60">{entries.length}</span>
          </button>
          {chips.map((c) => {
            const isActive = active === c.id;
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => setActive(isActive ? null : c.id)}
                aria-pressed={isActive}
                className={`rounded-full border px-3 py-1 text-xs ${
                  isActive
                    ? "border-zinc-900 bg-zinc-900 font-medium text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                    : "border-black/10 text-zinc-600 hover:bg-black/5 dark:border-white/15 dark:text-zinc-300 dark:hover:bg-white/10"
                }`}
              >
                {c.label} · <span className="opacity-60">{counts.get(c.id) ?? 0}</span>
              </button>
            );
          })}
        </div>
      )}

      {filtered.length === 0 && <p className="text-sm text-zinc-500">No essays tagged for this stage yet.</p>}

      {years.map((year) => (
        <section key={year} className="mb-8">
          <h2 className="mb-2 border-b border-black/10 pb-1 text-xs font-semibold uppercase tracking-widest text-zinc-400 dark:border-white/10">
            {year} · {groups.get(year)!.length}
          </h2>
          <ul>
            {groups.get(year)!.map((e) => (
              <li key={e.slug}>
                <Link
                  href={`/essays/${e.slug}`}
                  className="flex items-baseline justify-between gap-3 rounded-lg px-2 py-2 hover:bg-black/5 dark:hover:bg-white/5"
                >
                  <span className="min-w-0 font-medium hover:underline">{e.title}</span>
                  <span className="shrink-0 text-xs text-zinc-500">
                    {formatDateShort(e.date)} · {e.reading_time_min} min
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
