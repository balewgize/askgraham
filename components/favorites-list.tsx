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
      <h1
        className="font-serif text-2xl font-bold tracking-tight sm:text-3xl"
        style={{ fontFamily: "Georgia, serif" }}
      >
        Favorites
      </h1>
      <p className="mt-1 text-xs text-zinc-500">
        Saved in this browser only · <span className="opacity-60">{saved.length}</span>
      </p>

      {saved.length === 0 ? (
        <p className="mt-6 text-sm text-zinc-600 dark:text-zinc-400">
          Nothing saved yet. Hit <span className="font-medium">Save</span> on any essay and it will show up here.{" "}
          <Link href="/" className="underline hover:text-zinc-800 dark:hover:text-zinc-200">
            Browse all essays
          </Link>
        </p>
      ) : (
        <ul className="mt-4">
          {saved.map((e) => (
            <li key={e.slug} className="group flex items-center gap-1">
              <Link
                href={`/essays/${e.slug}`}
                className="flex min-w-0 flex-1 items-baseline justify-between gap-3 rounded-lg px-2 py-2 hover:bg-black/5 dark:hover:bg-white/5"
              >
                <span className="min-w-0 font-medium hover:underline">{e.title}</span>
                <span className="shrink-0 text-xs text-zinc-500">
                  {formatDateShort(e.date)} · {e.reading_time_min} min
                </span>
              </Link>
              <button
                type="button"
                onClick={() => setFavorite(e.slug, false)}
                aria-label={`Remove ${e.title} from favorites`}
                className="shrink-0 rounded p-1.5 text-orange-600 opacity-0 transition-opacity hover:bg-black/5 focus-visible:opacity-100 group-hover:opacity-100 dark:text-orange-400 dark:hover:bg-white/5"
              >
                <BookmarkIcon size={15} filled />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}