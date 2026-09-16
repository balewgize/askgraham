import Link from "next/link";
import type { ReactNode } from "react";
import { formatBytes, getCorpusManifest, type CorpusFile } from "@/lib/corpus";

export const dynamic = "force-static";

export const metadata = {
  title: "Take the essays anywhere — Ask Graham",
  description:
    "Download Paul Graham's essays as clean markdown and JSON, ready to import into NotebookLM, Claude, ChatGPT, Notion, or Obsidian.",
};

function fmtInt(n: number) {
  return n.toLocaleString("en-US");
}

function FileRow({ file }: { file: CorpusFile }) {
  return (
    <a
      href={`/corpus/${file.path}`}
      download
      className="flex items-baseline justify-between gap-3 rounded-lg border border-black/10 px-3 py-2 text-sm hover:bg-black/5 dark:border-white/15 dark:hover:bg-white/5"
    >
      <span className="min-w-0 font-medium">{file.label}</span>
      <span className="shrink-0 text-xs text-zinc-500">{formatBytes(file.bytes)} ↓</span>
    </a>
  );
}

function Tool({ name, blurb, children }: { name: string; blurb: string; children: ReactNode }) {
  return (
    <section className="mb-6 rounded-xl border border-black/10 p-4 dark:border-white/15">
      <h2 className="font-serif text-lg font-bold tracking-tight sm:text-xl" style={{ fontFamily: "Georgia, serif" }}>
        {name}
      </h2>
      <p className="mt-1 mb-3 text-sm text-zinc-600 dark:text-zinc-400">{blurb}</p>
      <div className="space-y-1.5">{children}</div>
    </section>
  );
}

export default async function CorpusPage() {
  const manifest = await getCorpusManifest();

  if (!manifest) {
    return (
      <div>
        <h1 className="font-serif text-2xl font-bold" style={{ fontFamily: "Georgia, serif" }}>
          Take the essays anywhere
        </h1>
        <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
          The export hasn&apos;t been generated yet. Run{" "}
          <code className="rounded bg-black/5 px-1 dark:bg-white/10">pnpm export:corpus</code>.
        </p>
      </div>
    );
  }

  const bundles = manifest.files.filter((f) => f.kind === "bundle");
  const all = manifest.files.find((f) => f.kind === "all");
  const jsonl = manifest.files.find((f) => f.kind === "jsonl");
  const zip = manifest.files.find((f) => f.kind === "zip");

  return (
    <div>
      <div className="mb-8">
        <h1 className="font-serif text-2xl font-bold tracking-tight sm:text-3xl" style={{ fontFamily: "Georgia, serif" }}>
          Take the essays anywhere
        </h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          All {fmtInt(manifest.essays)} essays, footnotes included, as clean markdown and JSON. Import them into your own
          AI notebook or notes app and ask away.
        </p>
      </div>

      <Tool
        name="NotebookLM"
        blurb="Add one decade at a time. Each file stays well under NotebookLM's 500,000-word limit, so imports won't fail."
      >
        {bundles.map((f) => (
          <FileRow key={f.path} file={f} />
        ))}
      </Tool>

      <Tool
        name="Claude"
        blurb="Add the decade files as knowledge in a Claude Project. Start with the eras you care about most."
      >
        {bundles.map((f) => (
          <FileRow key={f.path} file={f} />
        ))}
      </Tool>

      <Tool
        name="ChatGPT"
        blurb="One file with the whole catalog — ideal for a Project or a Custom GPT, which takes up to 2M tokens of knowledge."
      >
        {all && <FileRow file={all} />}
      </Tool>

      <Tool
        name="Notion & Obsidian"
        blurb="Download any essay as markdown from its page, or take all of them as a zip."
      >
        {zip && <FileRow file={zip} />}
      </Tool>

      <Tool
        name="Agents & scripts"
        blurb="Newline-delimited JSON — one full essay per line, for embeddings or your own tooling."
      >
        {jsonl && <FileRow file={jsonl} />}
      </Tool>

      <p className="mt-10 border-t border-black/10 pt-3 text-xs text-zinc-400 dark:border-white/10">
        Updated {manifest.generated.slice(0, 10)} · source:{" "}
        <a href={manifest.source} target="_blank" rel="noopener noreferrer" className="underline">
          paulgraham.com
        </a>{" "}
        · all essays © Paul Graham.{" "}
        <Link href="/" className="underline">
          Back to reading
        </Link>
      </p>
    </div>
  );
}
