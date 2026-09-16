import { readFile } from "node:fs/promises";
import path from "node:path";

export type CorpusFile = {
  path: string;
  bytes: number;
  words: number;
  kind: "all" | "bundle" | "jsonl" | "zip";
  label: string;
};

export type CorpusManifest = {
  generated: string;
  essays: number;
  words: number;
  source: string;
  files: CorpusFile[];
};

export async function getCorpusManifest(): Promise<CorpusManifest | null> {
  try {
    const raw = await readFile(path.join(process.cwd(), "public", "corpus", "manifest.json"), "utf-8");
    return JSON.parse(raw) as CorpusManifest;
  } catch {
    return null;
  }
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
