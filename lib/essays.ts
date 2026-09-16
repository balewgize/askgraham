import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

export type Footnote = { id: string; text: string };

export type Essay = {
  slug: string;
  title: string;
  url: string;
  date: string | null;
  word_count: number;
  reading_time_min: number;
  paragraphs: string[];
  footnotes: Footnote[];
};

export type IndexEntry = {
  slug: string;
  title: string;
  date: string | null;
  word_count: number;
  reading_time_min: number;
};

const DATA_DIR = path.join(process.cwd(), "data");
const ESSAYS_DIR = path.join(DATA_DIR, "essays");

const MONTHS: Record<string, number> = {
  January: 1,
  February: 2,
  March: 3,
  April: 4,
  May: 5,
  June: 6,
  July: 7,
  August: 8,
  September: 9,
  October: 10,
  November: 11,
  December: 12,
};

/** "September 2024" -> [2024, 9]; "1993"/null -> best-effort sortable key. */
export function dateKey(date: string | null): [number, number] {
  if (!date) return [0, 0];
  const m = date.match(/^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})$/);
  if (m) return [Number(m[2]), MONTHS[m[1]]];
  const y = date.match(/\b(19\d{2}|20\d{2})\b/);
  if (y) return [Number(y[1]), 0];
  return [0, 0];
}

/** Canonical display order: newest first, undated last. */
export function sortIndex(entries: IndexEntry[]): IndexEntry[] {
  return [...entries].sort((a, b) => {
    const [ay, am] = dateKey(a.date);
    const [by, bm] = dateKey(b.date);
    return by - ay || bm - am || a.title.localeCompare(b.title);
  });
}

export async function getIndex(): Promise<IndexEntry[]> {
  const raw = await readFile(path.join(DATA_DIR, "index.json"), "utf-8");
  return sortIndex(JSON.parse(raw) as IndexEntry[]);
}

export async function getSlugs(): Promise<string[]> {
  const files = await readdir(ESSAYS_DIR);
  return files.filter((f) => f.endsWith(".json")).map((f) => f.replace(/\.json$/, ""));
}

export async function getEssay(slug: string): Promise<Essay> {
  const raw = await readFile(path.join(ESSAYS_DIR, `${slug}.json`), "utf-8");
  return JSON.parse(raw) as Essay;
}

/** Prev/next in canonical display order. `prev` = newer, `next` = older. */
export async function getPrevNext(slug: string): Promise<{ prev: IndexEntry | null; next: IndexEntry | null }> {
  const index = await getIndex();
  const i = index.findIndex((e) => e.slug === slug);
  if (i < 0) return { prev: null, next: null };
  return { prev: index[i - 1] ?? null, next: index[i + 1] ?? null };
}
