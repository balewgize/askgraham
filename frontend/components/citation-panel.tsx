"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { formatDateShort } from "@/lib/dates";

type Essay = {
  slug: string;
  title: string;
  url: string;
  date: string | null;
  word_count: number;
  reading_time_min: number;
  paragraphs: string[];
  footnotes: { id: string; text: string }[];
};

type Props = {
  slug: string;
  start: number;
  end: number;
  onClose: () => void;
};

// Per-session cache: clicking several citations in one answer should not refetch.
const cache = new Map<string, Essay>();

async function fetchEssay(slug: string): Promise<Essay> {
  const response = await fetch(`/api/v1/essays/${slug}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as Essay;
}

export default function CitationPanel({ slug, start, end, onClose }: Props) {
  // The parent keys this component by slug, so the cached essay is the correct
  // initial state and the fetch below only runs on a miss.
  const [essay, setEssay] = useState<Essay | null>(() => cache.get(slug) ?? null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(() =>
    cache.has(slug) ? "ready" : "loading",
  );
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (cache.has(slug)) return;
    let cancelled = false;
    fetchEssay(slug)
      .then((loaded) => {
        if (cancelled) return;
        cache.set(slug, loaded);
        setEssay(loaded);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  // Scroll to the cited paragraph once it is on screen.
  useEffect(() => {
    if (status !== "ready") return;
    const container = scrollRef.current;
    const target = container?.querySelector<HTMLElement>(`#cite-p-${start}`);
    if (container && target) {
      container.scrollTo({ top: Math.max(0, target.offsetTop - 16), behavior: "smooth" });
    }
  }, [status, slug, start]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      role="dialog"
      aria-label={`Source: ${essay?.title ?? slug}`}
      className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-line bg-surface shadow-2xl sm:max-w-xl lg:sticky lg:top-20 lg:right-auto lg:bottom-auto lg:h-[calc(100dvh-5rem)] lg:w-[38rem] lg:shrink-0 lg:rounded-xl lg:border lg:shadow-lg"
    >
      <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="min-w-0">
          <p className="truncate font-serif text-base font-semibold tracking-tight">
            {essay?.title ?? "Loading…"}
          </p>
          {essay && (
            <p className="text-xs text-fg-subtle">
              {formatDateShort(essay.date)} · ¶{start}
              {end > start ? `–${end}` : ""}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Link
            href={`/essays/${slug}#p-${start}`}
            className="rounded-md px-2 py-1.5 text-sm text-fg-muted transition-colors hover:bg-fg/[0.06] hover:text-fg"
          >
            Open full essay
          </Link>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close source"
            className="rounded-md px-2 py-1.5 text-lg leading-none text-fg-subtle transition-colors hover:bg-fg/[0.06] hover:text-fg"
          >
            ✕
          </button>
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 sm:px-8">
        {status === "loading" && <p className="text-sm text-fg-subtle">Loading the essay…</p>}
        {status === "error" && (
          <p className="text-sm text-red-700 dark:text-red-400">Couldn&apos;t load this essay.</p>
        )}
        {essay && (
          <article className="max-w-[36em] font-serif text-[0.98rem] leading-relaxed [&>p]:mb-[1.05em]">
            {essay.paragraphs.map((paragraph, i) => {
              const cited = i >= start && i <= end;
              return (
                <p
                  key={i}
                  id={`cite-p-${i}`}
                  className={
                    cited
                      ? "-mx-2 scroll-mt-4 rounded bg-accent/10 px-2 py-0.5 text-fg"
                      : "scroll-mt-4"
                  }
                >
                  {paragraph}
                </p>
              );
            })}
          </article>
        )}
      </div>
    </aside>
  );
}
