import Link from "next/link";
import { getIndex } from "@/lib/essays";

export const dynamic = "force-static";

function yearOf(date: string | null): string {
  if (!date) return "Undated";
  const m = date.match(/\b(19\d{2}|20\d{2})\b/);
  return m ? m[1] : "Undated";
}

export default async function Home() {
  const index = await getIndex();
  const totalMin = index.reduce((a, e) => a + e.reading_time_min, 0);

  const groups = new Map<string, typeof index>();
  for (const e of index) {
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
      <div className="mb-8">
        <h1 className="font-serif text-3xl font-bold tracking-tight" style={{ fontFamily: "Georgia, serif" }}>
          Paul Graham&apos;s Essays
        </h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          {index.length} essays · ~{Math.round(totalMin / 60)} hours of reading · newest first
        </p>
        <p className="mt-1 text-xs text-zinc-400">
          Press <kbd className="rounded border border-black/10 px-1 dark:border-white/15">/</kbd> or{" "}
          <kbd className="rounded border border-black/10 px-1 dark:border-white/15">⌘K</kbd> to search ·{" "}
          <kbd className="rounded border border-black/10 px-1 dark:border-white/15">j</kbd>/
          <kbd className="rounded border border-black/10 px-1 dark:border-white/15">k</kbd> to move between essays
        </p>
      </div>

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
                  <span className="font-medium hover:underline">{e.title}</span>
                  <span className="shrink-0 text-xs text-zinc-500">
                    {e.date ?? "undated"} · {e.reading_time_min} min
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
