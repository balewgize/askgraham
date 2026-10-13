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
      className={`flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm transition-colors ${
        on
          ? "border-accent/45 text-accent hover:bg-accent/10"
          : "border-line-firm text-fg-muted hover:bg-fg/[0.06] hover:text-fg"
      }`}
    >
      <BookmarkIcon size={15} filled={on} />
      <span className="hidden sm:inline">{on ? "Saved" : "Save"}</span>
    </button>
  );
}