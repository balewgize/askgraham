"use client";

import Link from "next/link";
import { useMemo } from "react";
import { formatDateShort } from "@/lib/dates";
import type { IndexEntry } from "@/lib/essays";
import { BookmarkIcon } from "./icons";
import { setFavorite, useFavorites } from "./reader-prefs";

export default function FavoritesList({ entries }: { entries: IndexEntry[] }) {
  const slugs = useFavorites();

  // Newest save first; slugs missing from the index (e.g. a re-scrape) drop out.
  const saved = useMemo(() => {
    const bySlug = new Map(entries.map((e) => [e.slug, e]));
    return slugs
      .toReversed()
      .map((slug) => bySlug.get(slug))
      .filter((e): e is IndexEntry => e !== undefined);
  }, [entries, slugs]);

  return (
    <div>
      <h1 className="font-serif text-3xl font-semibold tracking-tight">Favorites</h1>
      <p className="mt-2 text-sm text-fg-subtle">
        Saved in this browser only · <span className="tabular-nums">{saved.length}</span>
      </p>

      {saved.length === 0 ? (
        <p className="mt-6 max-w-[46ch] text-[0.95rem] leading-relaxed text-fg-muted">
          Nothing saved yet. Hit <span className="font-medium text-fg">Save</span> on any essay and it will show up
          here.{" "}
          <Link href="/" className="text-fg underline underline-offset-2 hover:text-fg-muted">
            Browse all essays
          </Link>
        </p>
      ) : (
        <ul className="mt-6 divide-y divide-line border-b border-line">
          {saved.map((e) => (
            <li key={e.slug} className="group flex items-center gap-1">
              <Link
                href={`/essays/${e.slug}`}
                className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-lg px-2 py-3 transition-colors hover:bg-fg/[0.04] sm:flex-row sm:items-baseline sm:gap-4"
              >
                <span className="min-w-0 flex-1 font-medium text-fg">{e.title}</span>
                <span className="shrink-0 text-xs tabular-nums text-fg-subtle">
                  {formatDateShort(e.date)} · {e.reading_time_min} min
                </span>
              </Link>
              <button
                type="button"
                onClick={() => setFavorite(e.slug, false)}
                aria-label={`Remove ${e.title} from favorites`}
                className="shrink-0 rounded-md p-2.5 text-accent transition-colors hover:bg-accent/10 focus-visible:opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
              >
                <BookmarkIcon size={16} filled />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}