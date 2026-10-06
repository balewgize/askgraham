"use client";

import { BookmarkIcon } from "./icons";
import { toggleFavorite, useFavorites } from "./reader-prefs";

export default function FavoriteButton({ slug }: { slug: string }) {
  const on = useFavorites().includes(slug);
  return (
    <button
      type="button"
      onClick={() => toggleFavorite(slug)}
      aria-pressed={on}
      aria-label={on ? "Remove from favorites" : "Save to read later"}
      className={`flex items-center gap-1.5 rounded border px-2 py-1 ${
        on
          ? "border-orange-500/40 text-orange-700 dark:border-orange-400/40 dark:text-orange-300"
          : "border-black/10 hover:bg-black/5 dark:border-white/15 dark:hover:bg-white/10"
      }`}
    >
      <BookmarkIcon size={14} filled={on} />
      <span className="hidden sm:inline">{on ? "Saved" : "Save"}</span>
    </button>
  );
}