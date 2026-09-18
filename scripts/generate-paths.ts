/**
 * Curate reading paths through Paul Graham's essays with an LLM via OpenRouter.
 *
 * Usage:
 *   OPENROUTER_API_KEY=... pnpm paths
 *   pnpm paths -- --only=start-here   # regenerate one path
 *   pnpm paths -- --force             # ignore cache, regenerate everything
 *   pnpm paths -- --dry-run           # show what would run, no API calls
 *
 * Reads:  data/paths.spec.json, data/index.json, data/phases.json, data/paths.json (cache)
 * Writes: data/paths.json
 *
 * Cached per path on the spec + model, so re-runs only pay for edited intents.
 */
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { IndexEntry } from "../lib/essays";
import type { PathsFile, ReadingPath } from "../lib/paths";
import type { PhasesFile } from "../lib/phases";

try {
  (process as unknown as { loadEnvFile?: (p?: string) => void }).loadEnvFile?.(".env");
} catch {
  /* no .env file */
}

const DATA_DIR = path.join(process.cwd(), "data");
const OUT_PATH = path.join(DATA_DIR, "paths.json");

const BASE_URL = (process.env.OPENROUTER_BASE_URL ?? "https://openrouter.ai/api/v1").replace(/\/$/, "");
const MODEL = process.env.OPENROUTER_MODEL ?? "openai/gpt-oss-120b";
const API_KEY = process.env.OPENROUTER_API_KEY;
const MAX_ATTEMPTS = 3;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

type PathSpec = {
  id: string;
  title: string;
  subtitle: string;
  audience: string;
  intent: string;
  minSteps: number;
  maxSteps: number;
};

type Spec = { version: number; paths: PathSpec[] };

type Draft = { description: string; steps: { slug: string; note: string }[] };

const hashSpec = (spec: PathSpec) =>
  createHash("sha256").update(JSON.stringify(spec) + MODEL).digest("hex").slice(0, 16);

function catalog(entries: IndexEntry[], phases: PhasesFile): string {
  return entries
    .map((e) => {
      const p = phases.essays[e.slug];
      const tags = p?.phases.join(",") ?? "untagged";
      const why = p?.why ?? "";
      return `- ${e.slug} | ${e.title} (${e.date ?? "undated"}, ${e.reading_time_min} min) [${tags}] ${why}`;
    })
    .join("\n");
}

function buildPrompt(spec: PathSpec, entries: IndexEntry[], phases: PhasesFile) {
  const system = `You curate reading paths through Paul Graham's essay catalog for new readers.

You are given the full catalog. Each line is: slug | title (date, reading time) [stage tags] one-line summary.

Pick essays and order them into a path. Rules:
- Use only slugs that appear in the catalog. Never invent one.
- Return exactly one entry per essay. No duplicates.
- First essay: short, self-contained, zero prior knowledge required.
- Order so ideas build progressively; put foundational or widely cited essays before essays that assume them.
- Skip dated, news-pegged, or purely historical pieces unless they define a lasting idea.
- No two essays should make the same point.
- "note": one concrete sentence, max 22 words, telling the reader why this essay is here and why now. No filler.
- "description": 2 sentences describing the path's arc, max 45 words.`;

  const user = `Path: ${spec.title} — ${spec.subtitle}
Audience: ${spec.audience}
Goal: ${spec.intent}
Choose between ${spec.minSteps} and ${spec.maxSteps} essays.

Catalog:
${catalog(entries, phases)}`;
  return { system, user };
}

function extractJson(text: string): unknown {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const raw = fenced ? fenced[1] : text;
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start < 0 || end < 0) throw new Error("no JSON object in response");
  return JSON.parse(raw.slice(start, end + 1));
}

async function generateOnce(spec: PathSpec, entries: IndexEntry[], phases: PhasesFile): Promise<Draft> {
  const { system, user } = buildPrompt(spec, entries, phases);
  const slugs = entries.map((e) => e.slug);
  const res = await fetch(`${BASE_URL}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://askgraham.vercel.app",
      "X-Title": "Ask Graham path curator",
    },
    body: JSON.stringify({
      model: MODEL,
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "reading_path",
          strict: true,
          schema: {
            type: "object",
            properties: {
              description: { type: "string" },
              steps: {
                type: "array",
                minItems: spec.minSteps,
                maxItems: spec.maxSteps,
                items: {
                  type: "object",
                  properties: {
                    slug: { type: "string", enum: slugs },
                    note: { type: "string" },
                  },
                  required: ["slug", "note"],
                  additionalProperties: false,
                },
              },
            },
            required: ["description", "steps"],
            additionalProperties: false,
          },
        },
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
  const parsed = extractJson(content) as { description?: unknown; steps?: unknown };

  const description =
    typeof parsed.description === "string" ? parsed.description.trim().replace(/\s+/g, " ") : "";
  if (!description) throw new Error("empty description returned");

  const valid = new Set(slugs);
  const seen = new Set<string>();
  const steps: { slug: string; note: string }[] = [];
  if (Array.isArray(parsed.steps)) {
    for (const raw of parsed.steps) {
      const s = raw as { slug?: unknown; note?: unknown };
      if (typeof s.slug !== "string" || !valid.has(s.slug) || seen.has(s.slug)) continue;
      seen.add(s.slug);
      const note = typeof s.note === "string" ? s.note.trim().replace(/\s+/g, " ") : "";
      steps.push({ slug: s.slug, note });
    }
  }
  if (steps.length === 0) throw new Error("no valid steps returned");

  return { description, steps };
}

async function generate(spec: PathSpec, entries: IndexEntry[], phases: PhasesFile): Promise<Draft> {
  let lastError: Error = new Error("unreachable");
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      return await generateOnce(spec, entries, phases);
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
  const only = args.find((a) => a.startsWith("--only="))?.split("=")[1];

  const spec = JSON.parse(await readFile(path.join(DATA_DIR, "paths.spec.json"), "utf-8")) as Spec;
  const entries = JSON.parse(await readFile(path.join(DATA_DIR, "index.json"), "utf-8")) as IndexEntry[];
  const phases = JSON.parse(await readFile(path.join(DATA_DIR, "phases.json"), "utf-8")) as PhasesFile;

  let existing: PathsFile = { version: spec.version, model: MODEL, generated: "", paths: [] };
  try {
    existing = JSON.parse(await readFile(OUT_PATH, "utf-8"));
  } catch {
    /* first run */
  }
  const byId = new Map(existing.paths.map((p) => [p.id, p]));

  const todo = spec.paths.filter((p) => !only || p.id === only);
  const pending = todo.filter((p) => force || byId.get(p.id)?.hash !== hashSpec(p));

  console.log(`model: ${MODEL}`);
  console.log(`${spec.paths.length} paths · ${todo.length} selected · ${pending.length} to generate`);
  if (dryRun) {
    for (const p of pending) console.log(`  would generate ${p.id} (${p.minSteps}-${p.maxSteps} steps)`);
    console.log("dry run — no API calls, nothing written");
    return;
  }
  if (pending.length === 0) {
    console.log("nothing to do");
    return;
  }
  if (!API_KEY) {
    console.error("OPENROUTER_API_KEY is not set. Add it to .env or the environment.");
    process.exit(1);
  }

  const results = new Map(byId);
  const errors: string[] = [];
  for (const p of pending) {
    try {
      const draft = await generate(p, entries, phases);
      const readPath: ReadingPath = {
        id: p.id,
        title: p.title,
        subtitle: p.subtitle,
        description: draft.description,
        audience: p.audience,
        order: spec.paths.indexOf(p) + 1,
        steps: draft.steps,
        hash: hashSpec(p),
      };
      results.set(p.id, readPath);
      const minutes = draft.steps.reduce(
        (a, s) => a + (entries.find((e) => e.slug === s.slug)?.reading_time_min ?? 0),
        0,
      );
      console.log(`[${p.id}] ${draft.steps.length} essays · ~${minutes} min`);
      for (const s of draft.steps) console.log(`   ${s.slug} — ${s.note}`);
    } catch (err) {
      errors.push(`${p.id}: ${(err as Error).message}`);
      console.warn(`FAIL ${p.id}: ${(err as Error).message}`);
    }
  }

  const paths = spec.paths
    .map((p) => results.get(p.id))
    .filter((p): p is ReadingPath => Boolean(p))
    .map((p, i) => ({ ...p, order: i + 1 }));

  await writeFile(
    OUT_PATH,
    JSON.stringify({ version: spec.version, model: MODEL, generated: new Date().toISOString(), paths }, null, 2),
  );
  console.log(`wrote data/paths.json · ${paths.length} paths`);

  if (errors.length > 0) {
    console.error(`${errors.length} failed — rerun to retry them`);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
