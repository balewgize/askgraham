import { readFile } from "node:fs/promises";
import path from "node:path";

export type Phase = {
  id: string;
  label: string;
  order: number;
  description: string;
};

export type Taxonomy = {
  version: number;
  phases: Phase[];
};

export type EssayPhase = {
  phases: string[];
  why: string;
  hash: string;
};

export type PhasesFile = {
  taxonomyVersion: number;
  model: string;
  generated: string;
  essays: Record<string, EssayPhase>;
};

const DATA_DIR = path.join(process.cwd(), "data");

export async function getTaxonomy(): Promise<Taxonomy> {
  const raw = await readFile(path.join(DATA_DIR, "taxonomy.json"), "utf-8");
  return JSON.parse(raw) as Taxonomy;
}

/** Null until `pnpm classify` has been run at least once. */
export async function getPhases(): Promise<PhasesFile | null> {
  try {
    const raw = await readFile(path.join(DATA_DIR, "phases.json"), "utf-8");
    return JSON.parse(raw) as PhasesFile;
  } catch {
    return null;
  }
}
