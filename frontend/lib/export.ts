import { readFile } from "node:fs/promises";
import path from "node:path";

export type ExportFile = {
  path: string;
  bytes: number;
  words: number;
  kind: "all" | "bundle" | "jsonl" | "zip" | "path";
  label: string;
};

export type ExportManifest = {
  generated: string;
  essays: number;
  words: number;
  source: string;
  files: ExportFile[];
};

export async function getExportManifest(): Promise<ExportManifest | null> {
  try {
    const raw = await readFile(path.join(process.cwd(), "public", "export", "manifest.json"), "utf-8");
    return JSON.parse(raw) as ExportManifest;
  } catch {
    return null;
  }
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
