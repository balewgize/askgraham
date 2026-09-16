"use client";

import { Document } from "flexsearch";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { formatDateShort } from "@/lib/dates";
import { SearchIcon } from "./icons";

type Meta = { slug: string; title: string; date: string | null; reading_time_min: number };

// Must match scripts/build-search-index.ts SEARCH_OPTIONS.
function createIndex() {
  return new Document({
    document: {
      id: "slug",
      index: [
        { field: "title", tokenize: "forward" },
        { field: "body", tokenize: "strict" },
      ],
    },
  });
}

type Result = Meta & { via: "title" | "body" };

async function loadIndex(): Promise<{ index: ReturnType<typeof createIndex>; meta: Map<string, Meta> }> {
  const index = createIndex();
  const [manifest, metaJson] = await Promise.all([
    fetch("/search-index/manifest.json").then((r) => r.json() as Promise<{ keys: string[] }>),
    fetch("/search-index/meta.json").then((r) => r.json() as Promise<Meta[]>),
  ]);
  await Promise.all(
    manifest.keys.map(async (key) => {
      const data = await fetch(`/search-index/${key}.json`).then((r) => r.json());
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (index as any).import(key, data);
    }),
  );
  return { index, meta: new Map(metaJson.map((m) => [m.slug, m])) };
}

let cached: Promise<{ index: ReturnType<typeof createIndex>; meta: Map<string, Meta> }> | null = null;

function searchAll(
  index: ReturnType<typeof createIndex>,
  meta: Map<string, Meta>,
  q: string,
  limit = 12,
): Result[] {
  const raw = index.search(q, { limit }) as unknown as
    | string[]
    | { field?: string; result: string[] }[];
  const titleHits: string[] = [];
  const bodyHits: string[] = [];
  if (Array.isArray(raw) && raw.length > 0 && typeof raw[0] === "string") {
    bodyHits.push(...(raw as string[]));
  } else {
    for (const group of raw as { field?: string; result: string[] }[]) {
      if (group.field === "title") titleHits.push(...group.result);
      else bodyHits.push(...group.result);
    }
  }
  const seen = new Set<string>();
  const out: Result[] = [];
  for (const slug of [...titleHits, ...bodyHits]) {
    if (seen.has(slug)) continue;
    seen.add(slug);
    const m = meta.get(slug);
    if (m) out.push({ ...m, via: titleHits.includes(slug) ? "title" : "body" });
    if (out.length >= limit) break;
  }
  return out;
}

export default function SearchPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [active, setActive] = useState(0);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const inputRef = useRef<HTMLInputElement>(null);

  const ensureLoaded = useCallback(() => {
    if (!cached) {
      setStatus("loading");
      cached = loadIndex()
        .then((v) => {
          setStatus("ready");
          return v;
        })
        .catch((e) => {
          console.warn("search index load failed", e);
          setStatus("error");
          cached = null;
          throw e;
        });
    }
    return cached;
  }, []);

  const openPalette = useCallback(() => {
    setQuery("");
    setResults([]);
    setActive(0);
    setOpen(true);
    ensureLoaded().catch(() => {});
  }, [ensureLoaded]);

  // Global shortcuts: Cmd/Ctrl+K toggles, "/" opens (outside inputs).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
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

  // Debounced search.
  useEffect(() => {
    if (!open || query.trim().length < 2) return;
    const t = setTimeout(() => {
      ensureLoaded()
        .then(({ index, meta }) => {
          setResults(searchAll(index, meta, query.trim()));
          setActive(0);
        })
        .catch(() => {});
    }, 120);
    return () => clearTimeout(t);
  }, [query, open, ensureLoaded]);

  const go = useCallback(
    (slug: string) => {
      setOpen(false);
      router.push(`/essays/${slug}`);
    },
    [router],
  );

  // The footer only needs its own top border when something sits between it and the input.
  const resultsAreaVisible = status === "loading" || status === "error" || query.trim().length >= 2;

  return (
    <>
      <button
        type="button"
        onClick={openPalette}
        className="flex items-center gap-1.5 rounded-md border border-black/10 px-2 py-1.5 text-xs text-zinc-600 hover:bg-black/5 dark:border-white/15 dark:text-zinc-300 dark:hover:bg-white/10"
        aria-label="Search essays"
      >
        <SearchIcon size={15} />
        <span className="hidden sm:inline">Search</span>
        <kbd className="hidden rounded border border-black/10 px-1 text-[10px] text-zinc-400 md:inline dark:border-white/15">
          ⌘K
        </kbd>
      </button>
      {open &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh] dark:bg-black/60"
            onMouseDown={(e) => {
              if (e.target === e.currentTarget) setOpen(false);
            }}
            role="presentation"
          >
          <div
            className="flex max-h-full w-full max-w-xl flex-col overflow-hidden rounded-xl border border-black/10 bg-white shadow-2xl dark:border-white/15 dark:bg-zinc-800"
            role="dialog"
            aria-modal="true"
            aria-label="Search essays"
          >
            <div className="flex items-center gap-2 border-b border-black/10 px-4 dark:border-white/10">
              <SearchIcon size={16} className="shrink-0 text-zinc-400" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  if (e.target.value.trim().length < 2) setResults([]);
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
                placeholder="Search all essays… (title + full text)"
                className="w-full bg-transparent py-3 text-sm outline-none"
              />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-1">
              {status === "loading" && <p className="px-3 py-4 text-xs text-zinc-500">Loading search index…</p>}
              {status === "error" && <p className="px-3 py-4 text-xs text-red-500">Search index failed to load.</p>}
              {status === "ready" && query.trim().length >= 2 && results.length === 0 && (
                <p className="px-3 py-4 text-xs text-zinc-500">No matches.</p>
              )}
              {results.map((r, i) => (
                <button
                  key={r.slug}
                  type="button"
                  onClick={() => go(r.slug)}
                  onMouseEnter={() => setActive(i)}
                  className={`flex w-full items-baseline justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm ${
                    i === active ? "bg-black/5 dark:bg-white/10" : ""
                  }`}
                >
                  <span className="truncate font-medium">
                    {r.title}
                    {r.via === "body" && <span className="ml-2 text-[10px] font-normal text-zinc-400">in text</span>}
                  </span>
                  <span className="shrink-0 text-[11px] text-zinc-500">
                    {formatDateShort(r.date)} · {r.reading_time_min} min
                  </span>
                </button>
              ))}
            </div>
            <p
              className={`px-4 py-2 text-[13px] text-zinc-400 ${
                resultsAreaVisible ? "border-t border-black/10 dark:border-white/10" : ""
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
