"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Essay, IndexEntry } from "@/lib/essays";
import type { ResolvedPath } from "@/lib/paths";
import { CheckIcon, CopyIcon, DownloadIcon } from "./icons";
import FavoriteButton from "./favorite-button";
import {
  getFontScale,
  getProgress,
  setActivePath,
  setFontScale,
  setPathDone,
  setProgress,
  useActivePathId,
  usePathDone,
  type FontScale,
} from "./reader-prefs";

function FootnoteRef({ id, text }: { id: string; text: string }) {
  const [pinned, setPinned] = useState(false);
  const activate = () => {
    // Phones: jump to the full note below. Pointer devices: toggle the popover.
    if (window.matchMedia("(max-width: 639px)").matches) {
      document.getElementById(`fn-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setPinned((v) => !v);
  };
  return (
    <span className="group relative inline-block">
      <button
        type="button"
        onClick={activate}
        onBlur={() => setPinned(false)}
        aria-label={`Footnote ${id}`}
        className="mx-0.5 inline-block -translate-y-1 rounded px-0.5 align-super text-[0.7em] font-semibold text-accent transition-colors hover:bg-accent/15"
      >
        [{id}]
      </button>
      <span
        className={`absolute left-1/2 z-20 w-[min(18rem,80vw)] -translate-x-1/2 rounded-lg border border-line bg-overlay p-3 text-left font-sans text-[13px] font-normal leading-relaxed tracking-normal text-fg-muted shadow-xl ${
          pinned ? "block" : "hidden sm:group-hover:block sm:group-focus-within:block"
        }`}
        role="note"
      >
        <span className="mr-1 font-semibold text-fg">[{id}]</span>
        {text}
      </span>
    </span>
  );
}

function Paragraph({
  text,
  footnotes,
  id,
}: {
  text: string;
  footnotes: Map<string, string>;
  id: string;
}) {
  const parts = text.split(/\[(\d+)\]/g);
  return (
    <p id={id} className="scroll-mt-28">
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          footnotes.has(part) ? (
            <FootnoteRef key={i} id={part} text={footnotes.get(part)!} />
          ) : (
            <span key={i} className="text-fg-subtle">
              [{part}]
            </span>
          )
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </p>
  );
}

/** Presets drive the article's own font-size, so `34em` measure tracks along with it. */
const SIZES: Record<FontScale, { size: string; leading: number }> = {
  s: { size: "17px", leading: 1.7 },
  m: { size: "19px", leading: 1.75 },
  l: { size: "22px", leading: 1.8 },
};

const controlOff =
  "border-line-firm text-fg-muted transition-colors hover:bg-fg/[0.06] hover:text-fg";

export default function EssayReader({
  essay,
  prev,
  next,
  why,
  paths = [],
}: {
  essay: Essay;
  prev: IndexEntry | null;
  next: IndexEntry | null;
  why?: string;
  paths?: ResolvedPath[];
}) {
  const router = useRouter();
  const [scale, setScale] = useState<FontScale>(getFontScale);
  const [copied, setCopied] = useState(false);
  const [readPct, setReadPct] = useState(0);
  const storedPathId = useActivePathId();
  const restored = useRef(false);
  const footnoteMap = useMemo(() => new Map(essay.footnotes.map((f) => [f.id, f.text])), [essay.footnotes]);

  // The path this essay belongs to, and this essay's place in it.
  const membership = paths.find((p) => p.steps.some((s) => s.slug === essay.slug)) ?? null;
  const activePathId =
    storedPathId && paths.some((p) => p.id === storedPathId)
      ? storedPathId
      : membership?.id ?? paths[0]?.id ?? null;
  const activePath = activePathId ? paths.find((p) => p.id === activePathId) ?? null : null;
  const pathIndex = activePath ? activePath.steps.findIndex((s) => s.slug === essay.slug) : -1;
  const inActivePath = pathIndex >= 0;
  const pathPrev = activePath && pathIndex > 0 ? activePath.steps[pathIndex - 1] : null;
  const pathNext = activePath && pathIndex >= 0 ? activePath.steps[pathIndex + 1] ?? null : null;

  // Ribbon shows the active path if we're in it, otherwise any path this essay belongs to.
  const ribbonPath = inActivePath ? activePath : membership;
  const ribbonIndex = ribbonPath ? ribbonPath.steps.findIndex((s) => s.slug === essay.slug) : -1;
  const ribbonDone = usePathDone(ribbonPath?.id ?? "");
  // Only count slugs still in the path — stale entries can survive a re-scrape.
  const ribbonCount = ribbonPath
    ? ribbonPath.steps.filter((s) => ribbonDone.includes(s.slug)).length
    : 0;
  const navPrev: { slug: string; title: string } | null = inActivePath ? pathPrev : prev;
  const navNext: { slug: string; title: string } | null = inActivePath ? pathNext : next;

  // Remember the fallback path so j/k follows the intended order.
  useEffect(() => {
    if (activePathId && activePathId !== storedPathId) setActivePath(activePathId);
  }, [activePathId, storedPathId]);

  const copyMarkdown = async () => {
    try {
      const md = await fetch(`/export/md/${essay.slug}.md`).then((r) => r.text());
      await navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable — the Download link still works */
    }
  };

  // Restore reading position once.
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const y = getProgress(essay.slug);
    if (y > 200) requestAnimationFrame(() => window.scrollTo(0, y));
  }, [essay.slug]);

  // Persist reading position (throttled) and mark path steps read at the end.
  useEffect(() => {
    let t: ReturnType<typeof setTimeout> | null = null;
    const onScroll = () => {
      if (t) return;
      t = setTimeout(() => {
        t = null;
        setProgress(essay.slug, window.scrollY);
        const atEnd = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 240;
        if (atEnd && activePath) setPathDone(activePath.id, essay.slug, true);
      }, 800);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (t) clearTimeout(t);
    };
  }, [essay.slug, activePath]);

  // Progress bar — rAF-throttled so it tracks the scrollbar without re-rendering per event.
  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      const span = document.documentElement.scrollHeight - window.innerHeight;
      setReadPct(span > 0 ? Math.min(100, Math.max(0, (window.scrollY / span) * 100)) : 0);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [essay.slug]);

  // j/k navigation: within the active path when there is one, otherwise by date.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const nextSlug = inActivePath ? pathNext?.slug : next?.slug;
      const prevSlug = inActivePath ? pathPrev?.slug : prev?.slug;
      if (e.key === "j" && nextSlug) router.push(`/essays/${nextSlug}`);
      else if (e.key === "k" && prevSlug) router.push(`/essays/${prevSlug}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, prev, next, inActivePath, pathPrev, pathNext]);

  const { size, leading } = SIZES[scale];

  return (
    <div>
      <div
        className="fixed inset-x-0 top-[var(--header-h,53px)] z-30 h-0.5"
        role="progressbar"
        aria-label="Reading progress"
        aria-valuenow={Math.round(readPct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full bg-accent transition-[width] duration-150" style={{ width: `${readPct}%` }} />
      </div>

      {why && (
        <div className="mb-6 max-w-[34em] border-l-2 border-line-firm pl-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-subtle">Why read this</p>
          <p className="mt-1 font-serif text-[1.05rem] italic leading-relaxed text-fg-muted">{why}</p>
        </div>
      )}

      {ribbonPath && ribbonIndex >= 0 && (
        <div className="mb-8 max-w-[34em]">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-subtle">Reading path</p>
            <p className="text-xs tabular-nums text-fg-subtle">
              Step {ribbonIndex + 1} of {ribbonPath.steps.length} · {ribbonCount} read
            </p>
          </div>
          <Link
            href={`/paths/${ribbonPath.id}`}
            className="mt-1 inline-block font-medium text-accent underline decoration-accent/35 underline-offset-4 transition-colors hover:decoration-accent"
          >
            {ribbonPath.title}
          </Link>
          <div className="mt-2.5 h-1 w-full overflow-hidden rounded-full bg-fg/10">
            <div
              className="h-full rounded-full bg-accent transition-[width] duration-300"
              style={{ width: `${Math.round((ribbonCount / ribbonPath.steps.length) * 100)}%` }}
            />
          </div>
        </div>
      )}

      <div className="mb-7 flex max-w-[34em] flex-wrap items-center justify-between gap-3 border-y border-line py-2.5">
        <div className="flex items-center gap-1.5">
          <FavoriteButton slug={essay.slug} />
          <button
            type="button"
            onClick={copyMarkdown}
            aria-label="Copy essay as markdown"
            className={`flex min-h-9 items-center gap-1.5 rounded-md border px-3 text-sm ${controlOff}`}
          >
            {copied ? <CheckIcon size={15} /> : <CopyIcon size={15} />}
            <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
          </button>
          <a
            href={`/export/md/${essay.slug}.md`}
            download
            aria-label="Download essay as markdown"
            className={`flex min-h-9 items-center gap-1.5 rounded-md border px-3 text-sm ${controlOff}`}
          >
            <DownloadIcon size={15} />
            <span className="hidden sm:inline">Download</span>
          </a>
        </div>

        <div className="flex items-center gap-1.5">
          <span id="text-size-label" className="text-xs text-fg-subtle">
            Text size
          </span>
          <div className="flex overflow-hidden rounded-md border border-line-firm" role="group" aria-labelledby="text-size-label">
            {(["s", "m", "l"] as FontScale[]).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  setScale(s);
                  setFontScale(s);
                }}
                aria-pressed={scale === s}
                className={`min-h-9 min-w-9 px-2 text-sm transition-colors ${
                  scale === s ? "bg-fg font-semibold text-surface" : "text-fg-muted hover:bg-fg/[0.06] hover:text-fg"
                }`}
              >
                <span aria-hidden="true">{s === "s" ? "A−" : s === "m" ? "A" : "A+"}</span>
                <span className="sr-only">{s === "s" ? "Small" : s === "m" ? "Medium" : "Large"} text size</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <article
        className="max-w-[34em] font-serif text-fg [&>p]:mb-[1.15em]"
        style={{ fontSize: size, lineHeight: leading }}
      >
        {essay.paragraphs.map((p, i) => (
          <Paragraph key={i} id={`p-${i}`} text={p} footnotes={footnoteMap} />
        ))}
      </article>

      {essay.footnotes.length > 0 && (
        <section
          className="mt-12 max-w-[34em] border-t border-line pt-5"
          aria-label="Footnotes"
        >
          <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-subtle">Notes</h2>
          <ol className="space-y-2.5 font-serif text-[0.95rem] leading-relaxed text-fg-muted">
            {essay.footnotes.map((f) => (
              <li key={f.id} id={`fn-${f.id}`} className="scroll-mt-28">
                <span className="mr-2 font-semibold text-accent">[{f.id}]</span>
                {f.text}
              </li>
            ))}
          </ol>
        </section>
      )}

      <nav className="mt-12 max-w-[34em]" aria-label="Essay navigation">
        <div className="grid gap-2 border-t border-line pt-4 sm:grid-cols-2">
          {navPrev ? (
            <Link
              href={`/essays/${navPrev.slug}`}
              className="group min-h-16 rounded-lg border border-line px-4 py-3 transition-colors hover:border-line-firm hover:bg-fg/[0.04]"
            >
              <span className="block text-[11px] uppercase tracking-[0.12em] text-fg-subtle">
                ← Previous <span className="font-sans normal-case tracking-normal opacity-70">k</span>
              </span>
              <span className="mt-0.5 block font-medium leading-snug group-hover:underline">{navPrev.title}</span>
            </Link>
          ) : (
            <span />
          )}
          {navNext && (
            <Link
              href={`/essays/${navNext.slug}`}
              className="group min-h-16 rounded-lg border border-line px-4 py-3 text-right transition-colors hover:border-line-firm hover:bg-fg/[0.04]"
            >
              <span className="block text-[11px] uppercase tracking-[0.12em] text-fg-subtle">
                Next <span className="font-sans normal-case tracking-normal opacity-70">j</span> →
              </span>
              <span className="mt-0.5 block font-medium leading-snug group-hover:underline">{navNext.title}</span>
            </Link>
          )}
        </div>
        <p className="mt-3 text-xs text-fg-subtle">
          Press <Kbd>j</Kbd> or <Kbd>k</Kbd> to move between essays ·{" "}
          <Kbd>/</Kbd> to search
        </p>
      </nav>
    </div>
  );
}

function Kbd({ children }: { children: string }) {
  return (
    <kbd className="rounded border border-line px-1 font-sans text-[11px] leading-4 text-fg-subtle">
      {children}
    </kbd>
  );
}