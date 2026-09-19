/**
 * Export the scraped corpus into portable, tool-ready formats.
 *
 * Usage:
 *   pnpm export:corpus
 *
 * Output (public/export/):
 *   essays.md               all essays in one LLM-friendly markdown document
 *   essays.jsonl            one full essay JSON per line
 *   md/<slug>.md            one markdown file per essay
 *   notebooklm/<decade>.md  decade bundles, each far below NotebookLM's 500k-word cap
 *   askgraham-export.zip    essays.md + essays.jsonl + every md file
 *   manifest.json           counts, sizes and word totals for the download page
 */
import { zipSync, strToU8 } from "fflate";
import { mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { sortIndex, type Essay } from "../lib/essays";
import { getPaths } from "../lib/paths";

const DATA_DIR = path.join(process.cwd(), "data");
const ESSAYS_DIR = path.join(DATA_DIR, "essays");
const OUT_DIR = path.join(process.cwd(), "public", "export");
const SOURCE = "https://www.paulgraham.com/articles.html";

const fmtInt = (n: number) => n.toLocaleString("en-US");
const wordCount = (s: string) => s.split(/\s+/).filter(Boolean).length;
const fmtDate = (d: string | null) => d ?? "undated";

function decadeOf(date: string | null): string {
  const m = date?.match(/\b(19\d{2}|20\d{2})\b/);
  if (!m) return "undated";
  return `${Math.floor(Number(m[1]) / 10) * 10}s`;
}

function metaLine(essay: Essay): string {
  return `_${fmtDate(essay.date)} · ${fmtInt(essay.word_count)} words · ${essay.reading_time_min} min read · [original](${essay.url})_`;
}

/** Essay as markdown starting at `level` (`#` for standalone, `##` inside a bundle). */
function essayMarkdown(essay: Essay, level: number): string {
  const h = "#".repeat(level);
  const parts = [`${h} ${essay.title}`, metaLine(essay)];
  for (const p of essay.paragraphs) parts.push(p.trim());
  if (essay.footnotes.length > 0) {
    parts.push(`${"#".repeat(level + 1)} Notes`);
    parts.push(essay.footnotes.map((f) => `- **[${f.id}]** ${f.text.trim()}`).join("\n"));
  }
  return parts.join("\n\n");
}

function frontMatter(essay: Essay): string {
  const q = (s: string) => `"${s.replace(/"/g, '\\"')}"`;
  return [
    "---",
    `title: ${q(essay.title)}`,
    `slug: ${essay.slug}`,
    `date: ${essay.date ? q(essay.date) : "null"}`,
    `url: ${q(essay.url)}`,
    `word_count: ${essay.word_count}`,
    `reading_time_min: ${essay.reading_time_min}`,
    "---",
  ].join("\n");
}

function collection(title: string, subtitle: string, essays: Essay[]): string {
  const header = [`# ${title}`, `_${subtitle}_`];
  const body = essays.map((e) => essayMarkdown(e, 2));
  return [...header, "---", ...body].join("\n\n") + "\n";
}

type ManifestFile = {
  path: string;
  bytes: number;
  words: number;
  kind: "all" | "bundle" | "jsonl" | "zip" | "path";
  label: string;
};

async function main() {
  const slugFiles = (await readdir(ESSAYS_DIR)).filter((f) => f.endsWith(".json"));
  const all = await Promise.all(
    slugFiles.map(async (f) => JSON.parse(await readFile(path.join(ESSAYS_DIR, f), "utf-8")) as Essay),
  );
  const bySlug = new Map(all.map((e) => [e.slug, e]));
  const essays = sortIndex(all).map((e) => bySlug.get(e.slug)!);
  const totalWords = essays.reduce((a, e) => a + e.word_count, 0);

  await rm(OUT_DIR, { recursive: true, force: true });
  await mkdir(path.join(OUT_DIR, "md"), { recursive: true });
  await mkdir(path.join(OUT_DIR, "notebooklm"), { recursive: true });
  await mkdir(path.join(OUT_DIR, "paths"), { recursive: true });

  const files: ManifestFile[] = [];
  const zipEntries: Record<string, Uint8Array> = {};
  const write = async (relPath: string, content: string) => {
    await writeFile(path.join(OUT_DIR, relPath), content);
    return strToU8(content);
  };

  // All essays in one document.
  const merged =
    collection(
      "Paul Graham's Essays",
      `${fmtInt(essays.length)} essays · ${fmtInt(totalWords)} words · [source](${SOURCE})`,
      essays,
    );
  zipEntries["essays.md"] = await write("essays.md", merged);
  files.push({
    path: "essays.md",
    bytes: Buffer.byteLength(merged),
    words: wordCount(merged),
    kind: "all",
    label: `All ${fmtInt(essays.length)} essays (single file)`,
  });

  // One JSON object per line for scripts/agents.
  const jsonl = essays.map((e) => JSON.stringify(e)).join("\n") + "\n";
  zipEntries["essays.jsonl"] = await write("essays.jsonl", jsonl);
  files.push({ path: "essays.jsonl", bytes: Buffer.byteLength(jsonl), words: 0, kind: "jsonl", label: "essays.jsonl — one essay per line" });

  // Per-essay markdown with front-matter.
  for (const essay of essays) {
    const md = `${frontMatter(essay)}\n\n${essayMarkdown(essay, 1)}\n`;
    zipEntries[`md/${essay.slug}.md`] = await write(`md/${essay.slug}.md`, md);
  }

  // Decade bundles (each well under NotebookLM's 500k-word limit).
  const byDecade = new Map<string, Essay[]>();
  for (const essay of essays) {
    const d = decadeOf(essay.date);
    if (!byDecade.has(d)) byDecade.set(d, []);
    byDecade.get(d)!.push(essay);
  }
  const decades = [...byDecade.keys()].sort((a, b) => {
    if (a === "undated") return 1;
    if (b === "undated") return -1;
    return Number(b.slice(0, 4)) - Number(a.slice(0, 4));
  });
  for (const decade of decades) {
    const group = byDecade.get(decade)!;
    const words = group.reduce((a, e) => a + e.word_count, 0);
    const content = collection(
      `Paul Graham's Essays — ${decade}`,
      `${fmtInt(group.length)} essays · ${fmtInt(words)} words · [source](${SOURCE})`,
      group,
    );
    zipEntries[`notebooklm/${decade}.md`] = await write(`notebooklm/${decade}.md`, content);
    files.push({
      path: `notebooklm/${decade}.md`,
      bytes: Buffer.byteLength(content),
      words: wordCount(content),
      kind: "bundle",
      label: `${decade} essays`,
    });
  }

  // Reading paths: intro + ordered essays, notes included.
  const paths = await getPaths();
  for (const p of paths) {
    const steps = p.steps.filter((s) => bySlug.has(s.slug));
    const group = steps.map((s) => bySlug.get(s.slug)!);
    const intro = [
      `# ${p.title}`,
      `_${p.subtitle} — ${p.description}_`,
      `Suggested reading order (${group.length} essays):\n\n${steps
        .map((s, i) => `${i + 1}. **${bySlug.get(s.slug)!.title}** — ${s.note}`)
        .join("\n")}`,
    ];
    const content = [...intro, "---", ...group.map((e) => essayMarkdown(e, 2))].join("\n\n") + "\n";
    zipEntries[`paths/${p.id}.md`] = await write(`paths/${p.id}.md`, content);
    files.push({
      path: `paths/${p.id}.md`,
      bytes: Buffer.byteLength(content),
      words: wordCount(content),
      kind: "path",
      label: p.title,
    });
  }

  // Everything zipped.
  const zip = Buffer.from(zipSync(zipEntries, { level: 6 }));
  await writeFile(path.join(OUT_DIR, "askgraham-export.zip"), zip);
  files.push({
    path: "askgraham-export.zip",
    bytes: zip.byteLength,
    words: 0,
    kind: "zip",
    label: "All markdown files (.zip)",
  });

  const manifest = {
    generated: new Date().toISOString(),
    essays: essays.length,
    words: totalWords,
    source: SOURCE,
    files,
  };
  await writeFile(path.join(OUT_DIR, "manifest.json"), JSON.stringify(manifest, null, 2));

  console.log(
    `corpus: ${essays.length} essays, ${fmtInt(totalWords)} words, ${decades.length} decade bundles -> public/export/`,
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
