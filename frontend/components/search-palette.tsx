"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { formatDateShort } from "@/lib/dates";
import { iconButton } from "@/lib/ui";
import { SearchIcon } from "./icons";

/** One backend search hit. Shaped by `GET /api/v1/search`. */
type Result = {
  slug: string;
  title: string;
  date: string | null;
  reading_time_min: number;
  score: number;
  snippet: string;
  start_paragraph: number;
  end_paragraph: number;
  vector_rank: number | null;
  lexical_rank: number | null;
  title_rank: number | null;
  rerank_score: number | null;
};

// Short queries match almost everything and are not worth a round trip.
const MIN_QUERY = 2;
const RESULT_LIMIT = 12;
const DEBOUNCE_MS = 150;

/** The old palette shipped a FlexSearch shard per key; now it is one request.
 *
 * Reranking is off here on purpose. The cross-encoder is the expensive stage
 * (hundreds of ms to seconds on CPU) and this runs on every debounced
 * keystroke; RRF fusion alone is ~30ms and good enough for a palette. The
 * reranker stays on for chat and the evals, where the latency budget is larger.
 */
async function searchBackend(query: string, signal: AbortSignal): Promise<Result[]> {
  const params = new URLSearchParams({
    q: query,
    limit: String(RESULT_LIMIT),
    dedupe: "true",
    rerank: "false",
  });
  const response = await fetch(`/api/v1/search?${params}`, { signal });
  if (!response.ok) throw new Error(`search failed: HTTP ${response.status}`);
  const payload = (await response.json()) as { results: Result[] };
  return payload.results;
}

export default function SearchPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [active, setActive] = useState(0);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const inputRef = useRef<HTMLInputElement>(null);

  const openPalette = useCallback(() => {
    setQuery("");
    setResults([]);
    setActive(0);
    setStatus("idle");
    setOpen(true);
  }, []);

  // Global shortcuts: Cmd/Ctrl+K toggles, "/" opens (outside inputs).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing =
        target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) setOpen(false);
        else openPalette();
      } else if (e.key === "/" && !typing && !open) {
        e.preventDefault();
        openPalette();
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, openPalette]);

  useEffect(() => {
    if (!open) return;
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  // Debounced search against the backend. The cleanup aborts the in-flight
  // request, so a fast typist never sees a stale response overwrite a newer one.
  // All synchronous state changes happen in the input handler; the effect only
  // touches state from async callbacks, which the React lint rules require.
  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (q.length < MIN_QUERY) return;

    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchBackend(q, controller.signal)
        .then((hits) => {
          setResults(hits);
          setActive(0);
          setStatus("ready");
        })
        .catch((error) => {
          if (controller.signal.aborted) return;
          console.warn("search failed", error);
          setResults([]);
          setStatus("error");
        });
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, open]);

  const go = useCallback(
    (slug: string) => {
      setOpen(false);
      router.push(`/essays/${slug}`);
    },
    [router],
  );

  // The footer only needs its own top border when something sits between it and the input.
  const resultsAreaVisible = status === "loading" || status === "error" || query.trim().length >= MIN_QUERY;

  return (
    <>
      <button
        type="button"
        onClick={openPalette}
        className={`${iconButton} sm:w-auto sm:gap-2 sm:border sm:border-line-firm/60 sm:px-3`}
        aria-label="Search essays"
      >
        <SearchIcon size={16} />
        <span className="hidden sm:inline">Search</span>
        <kbd className="hidden rounded border border-line px-1 text-[10px] leading-4 text-fg-subtle md:inline">⌘K</kbd>
      </button>
      {open &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-start justify-center bg-black/45 p-4 pt-[12vh]"
            onMouseDown={(e) => {
              if (e.target === e.currentTarget) setOpen(false);
            }}
            role="presentation"
          >
            <div
              className="flex max-h-full w-full max-w-xl flex-col overflow-hidden rounded-xl border border-line bg-overlay shadow-2xl"
              role="dialog"
              aria-modal="true"
              aria-label="Search essays"
            >
              <div className="flex items-center gap-2.5 border-b border-line px-4">
                <SearchIcon size={16} className="shrink-0 text-fg-subtle" />
                <input
                  ref={inputRef}
                  value={query}
                  onChange={(e) => {
                    const value = e.target.value;
                    setQuery(value);
                    if (value.trim().length < MIN_QUERY) {
                      setResults([]);
                      setStatus("idle");
                    } else {
                      setStatus("loading");
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setActive((a) => Math.min(a + 1, results.length - 1));
                    } else if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setActive((a) => Math.max(a - 1, 0));
                    } else if (e.key === "Enter" && results[active]) {
                      go(results[active].slug);
                    }
                  }}
                  placeholder="Search all essays… (hybrid: meaning + exact words)"
                  className="w-full bg-transparent py-3.5 text-base text-fg outline-none focus-visible:outline-hidden! placeholder:text-fg-subtle"
                />
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
                {status === "loading" && <p className="px-3 py-4 text-sm text-fg-subtle">Searching…</p>}
                {status === "error" && (
                  <p className="px-3 py-4 text-sm text-red-700 dark:text-red-400">Search is unavailable.</p>
                )}
                {status === "ready" && query.trim().length >= MIN_QUERY && results.length === 0 && (
                  <p className="px-3 py-4 text-sm text-fg-subtle">No matches.</p>
                )}
                {results.map((r, i) => (
                  <button
                    key={r.slug}
                    type="button"
                    onClick={() => go(r.slug)}
                    onMouseEnter={() => setActive(i)}
                    className={`flex w-full flex-col gap-0.5 rounded-lg px-3 py-2.5 text-left transition-colors ${
                      i === active ? "bg-fg/[0.07]" : ""
                    }`}
                  >
                    <span className="flex w-full items-baseline justify-between gap-3">
                      <span className="min-w-0 truncate text-[0.95rem] font-medium">{r.title}</span>
                      <span className="shrink-0 text-xs tabular-nums text-fg-subtle">
                        {formatDateShort(r.date)} · {r.reading_time_min} min
                      </span>
                    </span>
                    {r.snippet && (
                      <span className="line-clamp-1 text-xs text-fg-subtle">{r.snippet}</span>
                    )}
                  </button>
                ))}
              </div>
              <p
                className={`px-4 py-2.5 text-xs text-fg-subtle ${
                  resultsAreaVisible ? "border-t border-line" : "border-t border-transparent"
                }`}
              >
                ↑↓ navigate · Enter open · Esc close
              </p>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
