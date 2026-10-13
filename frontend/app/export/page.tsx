import type { ReactNode } from "react";
import { formatBytes, getExportManifest, type ExportFile } from "@/lib/export";

export const dynamic = "force-static";

export const metadata = {
  title: "Take the essays anywhere",
  description:
    "Download Paul Graham's essays as clean markdown and JSON, ready to import into NotebookLM, Claude, ChatGPT, Notion, or Obsidian.",
  alternates: { canonical: "/export" },
};

function fmtInt(n: number) {
  return n.toLocaleString("en-US");
}

function FileRow({ file }: { file: ExportFile }) {
  return (
    <a
      href={`/export/${file.path}`}
      download
      className="flex items-baseline justify-between gap-3 rounded-lg border border-line px-3 py-2.5 text-sm transition-colors hover:border-line-firm hover:bg-fg/[0.04]"
    >
      <span className="min-w-0 font-medium">{file.label}</span>
      <span className="shrink-0 text-xs tabular-nums text-fg-subtle">{formatBytes(file.bytes)} ↓</span>
    </a>
  );
}

function Tool({ name, blurb, children }: { name: string; blurb: string; children: ReactNode }) {
  return (
    <section className="mb-5 rounded-xl border border-line p-5">
      <h2 className="font-serif text-lg font-semibold tracking-tight">{name}</h2>
      <p className="mt-1.5 mb-3.5 max-w-[52ch] text-sm leading-relaxed text-fg-muted">{blurb}</p>
      <div className="space-y-1.5">{children}</div>
    </section>
  );
}

export default async function ExportPage() {
  const manifest = await getExportManifest();

  if (!manifest) {
    return (
      <div>
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Take the essays anywhere</h1>
        <p className="mt-3 max-w-[46ch] text-[0.95rem] leading-relaxed text-fg-muted">
          The export hasn&apos;t been generated yet. Run{" "}
          <code className="rounded bg-fg/[0.07] px-1.5 py-0.5 font-mono text-[0.85em]">
            uv run python cli.py export
          </code>{" "}
          in <code className="font-mono text-[0.85em]">backend/</code>.
        </p>
      </div>
    );
  }

  const bundles = manifest.files.filter((f) => f.kind === "bundle");
  const paths = manifest.files.filter((f) => f.kind === "path");
  const all = manifest.files.find((f) => f.kind === "all");
  const jsonl = manifest.files.find((f) => f.kind === "jsonl");
  const zip = manifest.files.find((f) => f.kind === "zip");

  return (
    <div>
      <div className="mb-8 max-w-[46ch]">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Take the essays anywhere</h1>
        <p className="mt-2.5 text-[0.95rem] leading-relaxed text-fg-muted">
          All {fmtInt(manifest.essays)} essays, footnotes included, as clean markdown and JSON. Import them into your
          own AI notebook or notes app and ask away.
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
        name="Claude / ChatGPT / Gemini"
        blurb="One file with the whole catalog — add it as knowledge to a Claude Project, a ChatGPT Project/Custom GPT, or a Gemini Gem."
      >
        {all && <FileRow file={all} />}
      </Tool>

      <Tool
        name="Notion / Obsidian"
        blurb="Download any essay as markdown from its page, or take all of them as a zip."
      >
        {zip && <FileRow file={zip} />}
      </Tool>

      <Tool
        name="Agents / scripts"
        blurb="Newline-delimited JSON — one full essay per line, for embeddings or your own tooling."
      >
        {jsonl && <FileRow file={jsonl} />}
      </Tool>

      {paths.length > 0 && (
        <Tool
          name="Reading paths"
          blurb="Curated, ordered sequences of essays. Import one to follow a guided route from first idea to a working company."
        >
          {paths.map((f) => (
            <FileRow key={f.path} file={f} />
          ))}
        </Tool>
      )}

      <p className="mt-10 border-t border-line pt-4 text-sm text-fg-subtle">
        Updated {manifest.generated.slice(0, 10)} · source:{" "}
        <a
          href={manifest.source}
          target="_blank"
          rel="noopener noreferrer"
          className="text-fg-muted underline underline-offset-2 hover:text-fg"
        >
          paulgraham.com
        </a>{" "}
        · all essays © Paul Graham.
      </p>
    </div>
  );
}