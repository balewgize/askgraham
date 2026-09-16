/**
 * Build a client-side FlexSearch index at build time.
 *
 * Reads data/essays/*.json, writes:
 *   public/search-index/<key>.json   serialized FlexSearch Document export
 *   public/search-index/meta.json     [{slug, title, date, reading_time_min}]
 *
 * The search palette lazy-loads these and imports them into an identical
 * Document config — keep OPTIONS in sync with components/search-palette.tsx.
 */
import { Document } from "flexsearch";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

export const SEARCH_OPTIONS = {
  document: {
    id: "slug",
    index: [{ field: "title", tokenize: "forward" as const }, { field: "body", tokenize: "strict" as const }],
  },
};

async function main() {
  const essaysDir = path.join(process.cwd(), "data", "essays");
  const outDir = path.join(process.cwd(), "public", "search-index");
  await mkdir(outDir, { recursive: true });

  const files = (await readdir(essaysDir)).filter((f) => f.endsWith(".json"));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const index = new Document<any>(SEARCH_OPTIONS);
  const meta: { slug: string; title: string; date: string | null; reading_time_min: number }[] = [];

  for (const file of files) {
    const essay = JSON.parse(await readFile(path.join(essaysDir, file), "utf-8")) as {
      slug: string;
      title: string;
      date: string | null;
      reading_time_min: number;
      paragraphs: string[];
    };
    index.add({ slug: essay.slug, title: essay.title, body: essay.paragraphs.join("\n") });
    meta.push({ slug: essay.slug, title: essay.title, date: essay.date, reading_time_min: essay.reading_time_min });
  }

  const keys: string[] = [];
  await index.export((key, data) => {
    if (data === undefined) return;
    keys.push(key);
    return writeFile(path.join(outDir, `${key}.json`), data);
  });
  await writeFile(path.join(outDir, "meta.json"), JSON.stringify(meta));
  await writeFile(path.join(outDir, "manifest.json"), JSON.stringify({ keys }));

  console.log(`search index: ${files.length} docs, ${keys.length} keys -> public/search-index/`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
