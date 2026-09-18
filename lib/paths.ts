import { readFile } from "node:fs/promises";
import path from "node:path";
import { getIndex } from "./essays";

export type PathStep = {
  slug: string;
  note: string;
};

export type ReadingPath = {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  audience: string;
  order: number;
  steps: PathStep[];
  /** Cache key from the generator; ignored at render time. */
  hash?: string;
};

export type PathsFile = {
  version: number;
  model: string;
  generated: string;
  paths: ReadingPath[];
};

/** An essay's position in a path, for reader context and back-links. */
export type PathMembership = {
  id: string;
  title: string;
  step: number;
  total: number;
};

/** A path step joined with its essay metadata, safe to pass to client components. */
export type ResolvedStep = {
  slug: string;
  title: string;
  note: string;
  date: string | null;
  reading_time_min: number;
};

export type ResolvedPath = {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  audience: string;
  order: number;
  steps: ResolvedStep[];
};

const DATA_DIR = path.join(process.cwd(), "data");

/** Null until `pnpm paths` has produced data/paths.json. */
export async function getPathsFile(): Promise<PathsFile | null> {
  try {
    const raw = await readFile(path.join(DATA_DIR, "paths.json"), "utf-8");
    return JSON.parse(raw) as PathsFile;
  } catch {
    return null;
  }
}

export async function getPaths(): Promise<ReadingPath[]> {
  const file = await getPathsFile();
  if (!file) return [];
  return [...file.paths].sort((a, b) => a.order - b.order);
}

export async function getPath(id: string): Promise<ReadingPath | null> {
  const file = await getPathsFile();
  return file?.paths.find((p) => p.id === id) ?? null;
}

/** slug -> every path it appears in, with 1-based step position. */
export async function getPathMemberships(): Promise<Record<string, PathMembership[]>> {
  const paths = await getPaths();
  const out: Record<string, PathMembership[]> = {};
  for (const p of paths) {
    p.steps.forEach((step, i) => {
      if (!out[step.slug]) out[step.slug] = [];
      out[step.slug].push({ id: p.id, title: p.title, step: i + 1, total: p.steps.length });
    });
  }
  return out;
}

/** Paths with steps joined to essay metadata, for pages and client components. */
export async function getResolvedPaths(): Promise<ResolvedPath[]> {
  const [paths, index] = await Promise.all([getPaths(), getIndex()]);
  const bySlug = new Map(index.map((e) => [e.slug, e]));
  return paths.map((p) => ({
    ...p,
    steps: p.steps
      .filter((s) => bySlug.has(s.slug))
      .map((s) => {
        const e = bySlug.get(s.slug)!;
        return { slug: s.slug, title: e.title, note: s.note, date: e.date, reading_time_min: e.reading_time_min };
      }),
  }));
}
