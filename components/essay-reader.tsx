"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Essay, IndexEntry } from "@/lib/essays";
import { CheckIcon, CopyIcon, DownloadIcon } from "./icons";
import { getFontScale, getProgress, setFontScale, setProgress, type FontScale } from "./reader-prefs";

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
}: {
  essay: Essay;
  prev: IndexEntry | null;
  next: IndexEntry | null;
  why?: string;
}) {
  const router = useRouter();
  const [scale, setScale] = useState<FontScale>(getFontScale);
  const [copied, setCopied] = useState(false);
  const restored = useRef(false);
  const footnoteMap = new Map(essay.footnotes.map((f) => [f.id, f.text]));

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

  // Persist reading position (throttled).
  useEffect(() => {
    let t: ReturnType<typeof setTimeout> | null = null;
    const onScroll = () => {
      if (t) return;
      t = setTimeout(() => {
        t = null;
        setProgress(essay.slug, window.scrollY);
      }, 800);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (t) clearTimeout(t);
    };
  }, [essay.slug]);

  // j/k essay navigation.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "j" && next) router.push(`/essays/${next.slug}`);
      else if (e.key === "k" && prev) router.push(`/essays/${prev.slug}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, prev, next]);

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
          {prev && (
            <Link href={`/essays/${prev.slug}`} className="group block rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/5">
              <span className="text-[11px] uppercase tracking-wide text-zinc-400">← k · newer</span>
              <span className="block font-medium group-hover:underline">{prev.title}</span>
            </Link>
          )}
        </div>
        <div className="flex-1 text-right">
          {next && (
            <Link href={`/essays/${next.slug}`} className="group block rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/5">
              <span className="text-[11px] uppercase tracking-wide text-zinc-400">older · j →</span>
              <span className="block font-medium group-hover:underline">{next.title}</span>
            </Link>
          )}
        </div>
      </nav>
    </div>
  );
}
