/**
 * Classify essays by startup stage with an LLM via OpenRouter.
 *
 * Usage:
 *   OPENROUTER_API_KEY=... pnpm classify
 *   pnpm classify -- --limit 5      # classify at most 5 changed essays
 *   pnpm classify -- --force        # reclassify everything, ignore cache
 *   pnpm classify -- --dry-run      # show what would be classified, no API calls
 *
 * Reads:  data/taxonomy.json, data/essays/*.json, data/phases.json (cache)
 * Writes: data/phases.json
 *
 * Cost is tiny: the cache keys on essay content, so re-runs only pay for new
 * or edited essays. Change the prompt/taxonomy and pass --force to redo.
 */
import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import type { EssayPhase, Taxonomy } from "../lib/phases";
import { sortIndex, type Essay } from "../lib/essays";

try {
  (process as unknown as { loadEnvFile?: (p?: string) => void }).loadEnvFile?.(".env");
} catch {
  /* no .env file */
}

const DATA_DIR = path.join(process.cwd(), "data");
const ESSAYS_DIR = path.join(DATA_DIR, "essays");
const OUT_PATH = path.join(DATA_DIR, "phases.json");

const BASE_URL = (process.env.OPENROUTER_BASE_URL ?? "https://openrouter.ai/api/v1").replace(/\/$/, "");
const MODEL = process.env.OPENROUTER_MODEL ?? "openai/gpt-oss-120b";
const API_KEY = process.env.OPENROUTER_API_KEY;
const CONCURRENCY = Math.max(1, Number(process.env.CLASSIFY_CONCURRENCY ?? 4));
const MAX_ATTEMPTS = 3;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const hashEssay = (essay: Essay) =>
  createHash("sha256").update(essay.paragraphs.join("\n")).digest("hex").slice(0, 16);

function buildPrompt(essay: Essay, taxonomy: Taxonomy) {
  const phases = taxonomy.phases
    .map((p) => `- ${p.id}: ${p.label} — ${p.description}`)
    .join("\n");
  const system = `You label Paul Graham essays by the startup stage they help most.

Phases (choose one or more; put the single most relevant first):
${phases}

Rules:
- Use only the phase ids listed above.
- Include every stage the essay genuinely helps, not just one.
- Use "any" only for essays that are not stage-specific (craft, work, thinking).
- "why": one concrete sentence, max 20 words, telling a founder what they get from it. No filler like "This essay..."`;
  const user = `Title: ${essay.title}\nDate: ${essay.date ?? "unknown"}\n\n${essay.paragraphs.join("\n\n")}`;
  return { system, user };
}

function responseSchema(taxonomy: Taxonomy) {
  return {
    type: "object",
    properties: {
      phases: {
        type: "array",
        items: { type: "string", enum: taxonomy.phases.map((p) => p.id) },
        minItems: 1,
      },
      why: { type: "string" },
    },
    required: ["phases", "why"],
    additionalProperties: false,
  };
}

function extractJson(text: string): unknown {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const raw = fenced ? fenced[1] : text;
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start < 0 || end < 0) throw new Error("no JSON object in response");
  return JSON.parse(raw.slice(start, end + 1));
}

async function classifyOnce(essay: Essay, taxonomy: Taxonomy): Promise<{ phases: string[]; why: string }> {
  const { system, user } = buildPrompt(essay, taxonomy);
  const res = await fetch(`${BASE_URL}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://askgraham.vercel.app",
      "X-Title": "Ask Graham classifier",
    },
    body: JSON.stringify({
      model: MODEL,
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
      response_format: {
        type: "json_schema",
        json_schema: { name: "essay_phases", strict: true, schema: responseSchema(taxonomy) },
      },
    }),
  });

  if (!res.ok) {
    const body = (await res.text()).slice(0, 300);
    const err = new Error(`HTTP ${res.status}: ${body}`) as Error & { retryable?: boolean };
    err.retryable = res.status === 429 || res.status >= 500;
    throw err;
  }

  const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
  const content = data.choices?.[0]?.message?.content ?? "";
  const parsed = extractJson(content) as { phases?: unknown; why?: unknown };

  const validIds = new Set(taxonomy.phases.map((p) => p.id));
  const phases = Array.isArray(parsed.phases)
    ? [...new Set(parsed.phases.filter((p): p is string => typeof p === "string" && validIds.has(p)))]
    : [];
  if (phases.length === 0) throw new Error("no valid phases returned");
  const why = typeof parsed.why === "string" ? parsed.why.trim().replace(/\s+/g, " ") : "";
  if (!why) throw new Error("empty why returned");

  return { phases, why };
}

async function classify(essay: Essay, taxonomy: Taxonomy): Promise<EssayPhase> {
  let lastError: Error = new Error("unreachable");
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const result = await classifyOnce(essay, taxonomy);
      return { ...result, hash: hashEssay(essay) };
    } catch (err) {
      lastError = err as Error;
      const retryable = (lastError as Error & { retryable?: boolean }).retryable ?? true;
      if (!retryable || attempt === MAX_ATTEMPTS) break;
      await sleep(attempt * 1500);
    }
  }
  throw lastError;
}

async function main() {
  const args = process.argv.slice(2);
  const force = args.includes("--force");
  const dryRun = args.includes("--dry-run");
  const limit = Number(args.find((a) => a.startsWith("--limit"))?.split("=")[1]);

  const taxonomy = JSON.parse(await readFile(path.join(DATA_DIR, "taxonomy.json"), "utf-8")) as Taxonomy;
  const slugFiles = (await readdir(ESSAYS_DIR)).filter((f) => f.endsWith(".json"));
  const all = await Promise.all(
    slugFiles.map(async (f) => JSON.parse(await readFile(path.join(ESSAYS_DIR, f), "utf-8")) as Essay),
  );
  const bySlug = new Map(all.map((e) => [e.slug, e]));
  const essays = sortIndex(all).map((e) => bySlug.get(e.slug)!);

  let existing: { essays: Record<string, EssayPhase> } = { essays: {} };
  try {
    existing = JSON.parse(await readFile(OUT_PATH, "utf-8"));
  } catch {
    /* first run */
  }

  let todo = essays.filter((e) => force || existing.essays[e.slug]?.hash !== hashEssay(e));
  const skipped = essays.length - todo.length;
  if (Number.isFinite(limit) && limit > 0) todo = todo.slice(0, limit);

  console.log(`model: ${MODEL}`);
  console.log(`${essays.length} essays · ${skipped} cached · ${todo.length} to classify`);
  if (dryRun) {
    for (const e of todo) console.log(`  would classify ${e.slug}`);
    console.log("dry run — no API calls, nothing written");
    return;
  }
  if (todo.length === 0) {
    console.log("nothing to do");
    return;
  }
  if (!API_KEY) {
    console.error("OPENROUTER_API_KEY is not set. Add it to .env or the environment.");
    process.exit(1);
  }

  const results: Record<string, EssayPhase> = { ...existing.essays };
  const errors: string[] = [];
  let done = 0;
  let next = 0;

  async function worker() {
    while (next < todo.length) {
      const essay = todo[next++];
      try {
        results[essay.slug] = await classify(essay, taxonomy);
        done++;
        console.log(`[${done}/${todo.length}] ${essay.slug} -> ${results[essay.slug].phases.join(", ")}`);
      } catch (err) {
        errors.push(`${essay.slug}: ${(err as Error).message}`);
        console.warn(`FAIL ${essay.slug}: ${(err as Error).message}`);
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, todo.length) }, worker));

  // Keep only essays that still exist.
  const current = new Set(essays.map((e) => e.slug));
  const essaysOut: Record<string, EssayPhase> = {};
  for (const [slug, value] of Object.entries(results)) if (current.has(slug)) essaysOut[slug] = value;

  await writeFile(
    OUT_PATH,
    JSON.stringify(
      { taxonomyVersion: taxonomy.version, model: MODEL, generated: new Date().toISOString(), essays: essaysOut },
      null,
      2,
    ),
  );

  const counts = new Map<string, number>();
  for (const v of Object.values(essaysOut)) for (const p of v.phases) counts.set(p, (counts.get(p) ?? 0) + 1);
  const summary = taxonomy.phases.map((p) => `${p.id}=${counts.get(p.id) ?? 0}`).join("  ");
  console.log(`wrote data/phases.json · ${Object.keys(essaysOut).length} essays`);
  console.log(summary);

  if (errors.length > 0) {
    console.error(`${errors.length} failed — rerun to retry them`);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
