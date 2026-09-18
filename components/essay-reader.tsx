"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Essay, IndexEntry } from "@/lib/essays";
import type { ResolvedPath } from "@/lib/paths";
import { CheckIcon, CopyIcon, DownloadIcon } from "./icons";
import {
  getFontScale,
  getProgress,
  setActivePath,
  setFontScale,
  setPathDone,
  setProgress,
  useActivePathId,
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
        className="mx-0.5 inline-block -translate-y-1 rounded px-0.5 align-super text-[0.7em] font-semibold text-orange-700 hover:bg-orange-100 dark:text-orange-300 dark:hover:bg-orange-950"
      >
        [{id}]
      </button>
      <span
        className={`absolute left-1/2 z-20 w-[min(16rem,80vw)] -translate-x-1/2 rounded-lg border border-black/10 bg-white p-3 text-left text-[13px] font-normal normal-case leading-relaxed tracking-normal shadow-xl dark:border-white/15 dark:bg-zinc-800 ${
          pinned ? "block" : "hidden sm:group-hover:block sm:group-focus-within:block"
        }`}
        role="note"
      >
        <span className="mr-1 font-semibold">[{id}]</span>
        {text}
      </span>
    </span>
  );
}

function Paragraph({ text, footnotes }: { text: string; footnotes: Map<string, string> }) {
  const parts = text.split(/\[(\d+)\]/g);
  return (
    <p>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          footnotes.has(part) ? (
            <FootnoteRef key={i} id={part} text={footnotes.get(part)!} />
          ) : (
            <span key={i} className="text-zinc-500">
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

const SCALES: Record<FontScale, string> = {
  s: "text-[16.5px] leading-[1.75]",
  m: "text-[19px] leading-[1.8]",
  l: "text-[21.5px] leading-[1.85]",
};

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
  const storedPathId = useActivePathId();
  const restored = useRef(false);
  const footnoteMap = new Map(essay.footnotes.map((f) => [f.id, f.text]));

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
  const navPrev: { slug: string; title: string } | null = inActivePath ? pathPrev : prev;
  const navNext: { slug: string; title: string } | null = inActivePath ? pathNext : next;

  // Remember the fallback path so j/k follows the intended order.
  useEffect(() => {
    if (activePathId && activePathId !== storedPathId) setActivePath(activePathId);
  }, [activePathId, storedPathId]);

  const copyMarkdown = async () => {
    try {
      const md = await fetch(`/corpus/md/${essay.slug}.md`).then((r) => r.text());
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

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
        <span>Text size:</span>
        {(["s", "m", "l"] as FontScale[]).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setScale(s);
              setFontScale(s);
            }}
            aria-pressed={scale === s}
            className={`rounded border px-2 py-0.5 ${
              scale === s
                ? "border-orange-500 font-semibold text-orange-700 dark:text-orange-300"
                : "border-black/10 hover:bg-black/5 dark:border-white/15 dark:hover:bg-white/10"
            }`}
          >
            {s === "s" ? "A−" : s === "m" ? "A" : "A+"}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={copyMarkdown}
            aria-label="Copy essay as markdown"
            className="flex items-center gap-1.5 rounded border border-black/10 px-2 py-1 hover:bg-black/5 dark:border-white/15 dark:hover:bg-white/10"
          >
            {copied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
            <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
          </button>
          <a
            href={`/corpus/md/${essay.slug}.md`}
            download
            aria-label="Download essay as markdown"
            className="flex items-center gap-1.5 rounded border border-black/10 px-2 py-1 hover:bg-black/5 dark:border-white/15 dark:hover:bg-white/10"
          >
            <DownloadIcon size={14} />
            <span className="hidden sm:inline">Download</span>
          </a>
        </div>
      </div>

      {ribbonPath && ribbonIndex >= 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-orange-500/30 bg-orange-50/60 px-3 py-2 text-xs dark:border-orange-400/20 dark:bg-orange-950/20">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-orange-600 dark:text-orange-400">
            Reading path
          </span>
          <Link
            href={`/paths/${ribbonPath.id}`}
            className="font-medium text-orange-700 hover:underline dark:text-orange-300"
          >
            {ribbonPath.title}
          </Link>
          <span className="text-zinc-500">
            Step {ribbonIndex + 1} of {ribbonPath.steps.length}
          </span>
        </div>
      )}

      {why && (
        <div className="mb-6 max-w-[70ch] border-l-2 border-orange-500/60 pl-3">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">Why read this</p>
          <p className="mt-0.5 text-sm italic text-zinc-600 dark:text-zinc-300">{why}</p>
        </div>
      )}

      <article
        className={`max-w-[70ch] font-serif text-zinc-900 dark:text-zinc-100 ${SCALES[scale]} [&>p]:mb-[1.2em]`}
        style={{ fontFamily: "Georgia, 'Times New Roman', Charter, serif" }}
      >
        {essay.paragraphs.map((p, i) => (
          <Paragraph key={i} text={p} footnotes={footnoteMap} />
        ))}
      </article>

      {essay.footnotes.length > 0 && (
        <section className="mt-10 max-w-[70ch] border-t border-black/10 pt-4 dark:border-white/10" aria-label="Footnotes">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Notes</h2>
          <ol className="space-y-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            {essay.footnotes.map((f) => (
              <li key={f.id} id={`fn-${f.id}`} className="scroll-mt-24">
                <span className="mr-2 font-semibold">[{f.id}]</span>
                {f.text}
              </li>
            ))}
          </ol>
        </section>
      )}

      <nav className="mt-10 flex max-w-[70ch] items-stretch justify-between gap-3 border-t border-black/10 pt-4 text-sm dark:border-white/10">
        <div className="flex-1">
          {navPrev && (
            <Link href={`/essays/${navPrev.slug}`} className="group block rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/5">
              <span className="text-[11px] uppercase tracking-wide text-zinc-400">
                {inActivePath ? "← k · previous" : "← k · newer"}
              </span>
              <span className="block font-medium group-hover:underline">{navPrev.title}</span>
            </Link>
          )}
        </div>
        <div className="flex-1 text-right">
          {navNext && (
            <Link href={`/essays/${navNext.slug}`} className="group block rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/5">
              <span className="text-[11px] uppercase tracking-wide text-zinc-400">
                {inActivePath ? "next · j →" : "older · j →"}
              </span>
              <span className="block font-medium group-hover:underline">{navNext.title}</span>
            </Link>
          )}
        </div>
      </nav>
    </div>
  );
}
