"use client";

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import { formatDateShort } from "@/lib/dates";
import type { IndexEntry } from "@/lib/essays";
import Disclosure from "./disclosure";

type Chip = { id: string; label: string };
type EssayPhase = { phases: string[] };

function yearOf(date: string | null): string {
  if (!date) return "Undated";
  const m = date.match(/\b(19\d{2}|20\d{2})\b/);
  return m ? m[1] : "Undated";
}

const chipBase =
  "inline-flex min-h-8 items-center gap-1.5 rounded-full border px-3 text-sm transition-colors";
const chipOn = "border-fg bg-fg font-medium text-surface";
const chipOff = "border-line-firm text-fg-muted hover:bg-fg/[0.06] hover:text-fg";

export default function EssayIndex({
  entries,
  chips,
  essayPhases,
  hero,
}: {
  entries: IndexEntry[];
  chips: Chip[];
  essayPhases: Record<string, EssayPhase>;
  hero?: ReactNode;
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

  const activeLabel = chips.find((c) => c.id === active)?.label;

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-serif text-[1.75rem] font-semibold leading-tight tracking-tight sm:text-[2rem]">
          Paul Graham&apos;s Essays
        </h1>
        <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">
          Search {entries.length} essays, read them in full, or ask a question and get a cited answer.
        </p>
      </div>

      {hero}

      {chips.length > 0 && (
        <Disclosure
          className="mb-6"
          label="Filter"
          meta={active ? `${activeLabel} · ${filtered.length}` : `All stages · ${entries.length}`}
        >
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter essays by stage">
            <button
              type="button"
              onClick={() => setActive(null)}
              aria-pressed={active === null}
              className={`${chipBase} ${active === null ? chipOn : chipOff}`}
            >
              All
              <span className="tabular-nums opacity-60">{entries.length}</span>
            </button>
            {chips.map((c) => {
              const isActive = active === c.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setActive(isActive ? null : c.id)}
                  aria-pressed={isActive}
                  className={`${chipBase} ${isActive ? chipOn : chipOff}`}
                >
                  {c.label}
                  <span className="tabular-nums opacity-60">{counts.get(c.id) ?? 0}</span>
                </button>
              );
            })}
          </div>
          <p className="mt-2.5 text-xs text-fg-subtle" aria-live="polite">
            {active
              ? `${filtered.length} ${filtered.length === 1 ? "essay" : "essays"} in ${activeLabel}`
              : `${entries.length} essays, newest first`}
          </p>
        </Disclosure>
      )}

      {filtered.length === 0 && <p className="text-sm text-fg-muted">No essays tagged for this stage yet.</p>}

      {years.map((year) => (
        <section key={year} className="mb-2">
          <h2 className="sticky top-[var(--header-h,56px)] z-30 -mx-1 mb-1 flex items-baseline gap-2 border-b border-line bg-surface/90 px-1 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-fg-subtle backdrop-blur-sm">
            <span className="tabular-nums">{year}</span>
            <span className="font-normal normal-case tracking-normal opacity-70">
              {groups.get(year)!.length}
            </span>
          </h2>
          <ul className="divide-y divide-line border-b border-line">
            {groups.get(year)!.map((e) => (
              <li key={e.slug}>
                <Link
                  href={`/essays/${e.slug}`}
                  className="flex flex-col gap-0.5 rounded-lg px-2 py-3 transition-colors hover:bg-fg/[0.04] sm:flex-row sm:items-baseline sm:gap-4 sm:py-2.5"
                >
                  <span className="min-w-0 flex-1 font-medium text-fg">{e.title}</span>
                  <span className="shrink-0 text-xs tabular-nums text-fg-subtle">
                    {formatDateShort(e.date)} · {e.reading_time_min} min
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <p className="mt-8 text-xs text-fg-subtle">
        Press <Kbd>/</Kbd> or <Kbd>⌘K</Kbd> to search · <Kbd>j</Kbd> <Kbd>k</Kbd> to move between essays
      </p>
    </div>
  );
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-line px-1 font-sans text-[11px] leading-4 text-fg-subtle">
      {children}
    </kbd>
  );
}