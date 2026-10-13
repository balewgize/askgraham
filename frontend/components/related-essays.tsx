"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { formatDateShort } from "@/lib/dates";

type RelatedEssay = {
  slug: string;
  title: string;
  date: string | null;
  reading_time_min: number;
  similarity: number;
  start_paragraph: number;
  end_paragraph: number;
};

// Per-session cache, keyed by slug: navigating back to an essay should not
// refetch its neighbours. Mirrors the citation panel's cache.
const cache = new Map<string, RelatedEssay[]>();

async function fetchRelated(slug: string): Promise<RelatedEssay[]> {
  const response = await fetch(`/api/v1/essays/${slug}/related?limit=5`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const body = (await response.json()) as { results?: RelatedEssay[] };
  return body.results ?? [];
}

/**
 * "Related essays" for the reader. The list comes from the backend's chunk-vector
 * centroid, so it is a runtime call rather than snapshot data — the same
 * boundary search and chat live on. It renders nothing until (and unless) the
 * list arrives, because it is an enhancement, not page content.
 *
 * The parent keys this by slug so a navigation remounts it and the cached list
 * for the new essay is the correct initial state.
 */
export default function RelatedEssays({ slug }: { slug: string }) {
  const [items, setItems] = useState<RelatedEssay[]>(() => cache.get(slug) ?? []);

  useEffect(() => {
    if (cache.has(slug)) return;
    let cancelled = false;
    fetchRelated(slug)
      .then((related) => {
        if (cancelled) return;
        cache.set(slug, related);
        setItems(related);
      })
      .catch(() => {
        /* enhancement only — a failure leaves the section out entirely */
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (items.length === 0) return null;

  return (
    <section className="mt-10 max-w-[34em] border-t border-line pt-5" aria-label="Related essays">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-subtle">
        Related essays
      </h2>
      <ul>
        {items.map((item) => (
          <li key={item.slug}>
            <Link
              href={`/essays/${item.slug}`}
              className="-mx-2 flex items-baseline justify-between gap-4 rounded-md px-2 py-1.5 transition-colors hover:bg-fg/[0.04]"
            >
              <span className="font-medium leading-snug hover:underline">{item.title}</span>
              <span className="shrink-0 text-xs tabular-nums text-fg-subtle">
                {formatDateShort(item.date)} · {item.reading_time_min} min
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
