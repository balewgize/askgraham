/**
 * Scrape Paul Graham's essay catalog into local JSON.
 *
 * Usage:
 *   npx tsx scripts/scrape-essays.ts                          # full catalog
 *   npx tsx scripts/scrape-essays.ts --slugs say,ramenprofitable,foundermode
 *   npx tsx scripts/scrape-essays.ts --limit 5
 *
 * Output:
 *   data/essays/<slug>.json
 *   data/index.json
 */
import * as cheerio from "cheerio";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const BASE = "https://www.paulgraham.com";
const INDEX_URL = `${BASE}/articles.html`;
const UA =
  "askgraham-scraper/0.1 (personal learning project; Next.js reading tool; contact: owner of this local project)";
const DELAY_MS = 1500;

type IndexEntry = { title: string; url: string; slug: string };
type Footnote = { id: string; text: string };
type EssayJson = {
  slug: string;
  title: string;
  url: string;
  date: string | null;
  word_count: number;
  reading_time_min: number;
  paragraphs: string[];
  footnotes: Footnote[];
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function fetchHtml(url: string): Promise<string> {
  const res = await fetch(url, { headers: { "User-Agent": UA } });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  const buf = Buffer.from(await res.arrayBuffer());
  // Most pages are UTF-8; early-2000s pages (e.g. saynotes.html) are Windows-1252.
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(buf);
    return buf.toString("utf-8");
  } catch {
    return new TextDecoder("windows-1252").decode(buf);
  }
}

function parseIndex(html: string): IndexEntry[] {
  const $ = cheerio.load(html);
  const entries: IndexEntry[] = [];
  const seen = new Set<string>();

  // Essay rows are marked by the orange-square bullet gif; nav links lack it.
  $("td").each((_, td) => {
    const $td = $(td);
    if ($td.find('img[src*="the-reddits-2.gif"]').length === 0) return;
    $td.find('a[href$=".html"]').each((_, a) => {
      const href = $(a).attr("href")?.trim() ?? "";
      const title = $(a).text().trim().replace(/\s+/g, " ");
      if (!/^[a-z0-9_-]+\.html$/i.test(href) || !title) return;
      const slug = href.replace(/\.html$/i, "");
      if (seen.has(slug)) return;
      seen.add(slug);
      entries.push({ title, url: `${BASE}/${href}`, slug });
    });
  });

  if (entries.length === 0) throw new Error("Index parse found 0 essays — markup changed?");
  return entries;
}

const DATE_RE =
  /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(19\d{2}|20\d{2})\b/;
const NOTES_MARKER_RE = /<b>\s*Notes\s*<\/b>/i;
const THANKS_MARKER_RE = /<b>\s*Thanks\s*<\/b>/i;
// Notes may link to a relative ("saynotes.html") or absolute ("http://.../saynotes.html") page.
const NOTES_PAGE_RE = /href="(?:https?:\/\/www\.paulgraham\.com\/)?([a-z0-9_-]*notes\.html)"/i;

/** Text of an HTML fragment with <br> treated as whitespace (cheerio .text() concatenates them). */
function textWithBreaks(htmlFragment: string): string {
  const withSpaces = htmlFragment.replace(/<br\s*\/?>/gi, " ");
  return cheerio.load(withSpaces).text().replace(/\s+/g, " ").trim();
}

function blockText(htmlBlock: string): string {
  return textWithBreaks(htmlBlock);
}

/** Group split blocks into footnotes; continuation blocks (no leading [N]) append to previous. */
function blocksToFootnotes(blocks: string[]): Footnote[] {
  const footnotes: Footnote[] = [];
  for (const b of blocks) {
    if (THANKS_MARKER_RE.test(b)) break;
    const text = blockText(b);
    if (!text) continue;
    const $b = cheerio.load(b);
    const anchor = $b("a[name]").attr("name") ?? "";
    const anchorNum = anchor.match(/^f(\d+)n?$/i)?.[1];
    const leadNum = text.match(/^\[\s*(\d+)\s*\]/)?.[1];
    const id = anchorNum ?? leadNum;
    if (id) {
      const clean = text.replace(/^\[\s*\d+\s*\]\s*/, "").trim();
      if (clean) footnotes.push({ id: String(Number(id)), text: clean });
    } else if (footnotes.length > 0) {
      // Continuation of previous footnote (e.g. recipe <pre> paragraphs split apart).
      footnotes[footnotes.length - 1].text += `\n\n${text}`;
    }
  }
  return footnotes;
}

function parseInlineEssay(
  slug: string,
  url: string,
  html: string,
): { essay: EssayJson; notesPageHref: string | null } {
  const $ = cheerio.load(html);
  const title = $("title").first().text().trim().replace(/\s+/g, " ");
  if (!title) throw new Error("no <title>");

  // Main column: usually td width 435; one outlier (polls) uses 374.
  // The richest such td is the essay column (translation/footer tds are tiny).
  // NB: <br> must be treated as whitespace — .text() concatenates
  // "July 2009<br><br>Now..." into "July 2009Now...", hiding the date.
  const tds = $('td[width="435"], td[width="374"]').toArray();
  let $td: ReturnType<typeof $> | null = null;
  let bestLen = -1;
  for (const td of tds) {
    const len = textWithBreaks($(td).html() ?? "").length;
    if (len > bestLen) {
      bestLen = len;
      $td = $(td);
    }
  }
  if (!$td) throw new Error("essay column not found");

  // Date from the whole column (it may live in a different <font> than the body).
  const fullTextForDate = textWithBreaks($td.html() ?? "");
  const dateMatch = fullTextForDate.match(DATE_RE);
  let date: string | null = dateMatch ? dateMatch[0] : null;
  if (!date) {
    // Year-only dates (progbot: "1993 ..."); restricted to the head so body
    // years like "In 1960, ..." don't false-positive.
    const head = fullTextForDate.slice(0, 300);
    const yearOnly = head.match(/^\s*(19\d{2}|20\d{2})\b/) ?? head.match(/\b(19\d{2}|20\d{2})\b/);
    if (yearOnly) date = yearOnly[0].trim();
  }
  // date may legitimately be null (undated pages: fix, noop, rss stub).

  // Body: normally a single substantial <font>. Unclosed <p> tags (fix,
  // founders, rootsoflisp) make the parser split content across sibling
  // fonts — then use the whole column instead.
  const fonts = $td.find('font[size="2"]').toArray();
  const substantial = fonts.filter(
    (f) => textWithBreaks($(f).html() ?? "").length > 200,
  );
  let raw: string;
  if (substantial.length === 1) {
    const $f = $(substantial[0]);
    // Strip in-body ad tables (e.g. ramenprofitable YC banner), keep text flow.
    $f.find("table").remove();
    raw = $f.html() ?? "";
  } else {
    $td.find("table").remove();
    raw = $td.html() ?? "";
  }
  // Normalize <p> paragraph markup to the same breaks the splitter uses.
  raw = raw.replace(/<\/?p\b[^>]*>/gi, "<br><br>");
  const blocks = raw.split(/<br\s*\/?>\s*<br\s*\/?>/i);

  const notesIdx = blocks.findIndex((b) => NOTES_MARKER_RE.test(b));
  let notesPageHref: string | null = null;
  if (notesIdx >= 0) {
    const m = blocks[notesIdx].match(NOTES_PAGE_RE);
    if (m) notesPageHref = m[1];
  }

  const bodyEnd = notesIdx >= 0 ? notesIdx : blocks.length;
  const paragraphs: string[] = [];
  for (const b of blocks.slice(0, bodyEnd)) {
    if (THANKS_MARKER_RE.test(b)) continue;
    const text = blockText(b);
    if (!text) continue;
    if (/^\*\s*\*\s*\*$/.test(text)) continue; // "* * *" separator
    if (paragraphs.length === 0) {
      // Consume a leading date block ("July 2009", or date + first sentence
      // sharing one block); keep any trailing sentence text.
      const leadMonth = text.match(
        /^\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+(19\d{2}|20\d{2})\b/,
      );
      // Year-only (progbot: "1993 (This essay is from...)"): only strip when
      // parenthetical or date-only, so "1993 was the year..." prose survives.
      const leadYear =
        text.match(/^\s*(19\d{2}|20\d{2})\s*\(/) ?? (text.length < 30 ? text.match(/^\s*(19\d{2}|20\d{2})\b/) : null);
      const lead = leadMonth ?? leadYear;
      if (lead) {
        const rest = text.slice(lead[0].length).replace(/^\)?\s*/, "").trim();
        if (rest && !leadYear) paragraphs.push(rest);
        else if (rest) paragraphs.push(lead[0].includes("(") ? `(${rest}` : rest);
        continue;
      }
    }
    paragraphs.push(text);
  }
  if (paragraphs.length === 0) throw new Error("0 body paragraphs extracted");

  let footnotes: Footnote[] = [];
  if (notesIdx >= 0 && !notesPageHref) {
    footnotes = blocksToFootnotes(blocks.slice(notesIdx + 1));
  }

  const words = paragraphs.join(" ").split(/\s+/).filter(Boolean).length;
  return {
    essay: {
      slug,
      title,
      url,
      date,
      word_count: words,
      reading_time_min: Math.max(1, Math.ceil(words / 200)),
      paragraphs,
      footnotes,
    },
    notesPageHref,
  };
}

function parseNotesPage(html: string): Footnote[] {
  const $ = cheerio.load(html);
  const fonts = $('td[width="435"] font[size="2"]').toArray();
  const $font = fonts.length > 0 ? $(fonts[0]) : $("body");
  const raw = $font.html() ?? $.html();
  const blocks = raw.split(/<br\s*\/?>\s*<br\s*\/?>/i);
  // Drop the "(to Essay)" header block if present.
  const filtered = blocks.filter((b) => !/\(to\s*<a/i.test(b));
  return blocksToFootnotes(filtered);
}

async function scrapeOne(entry: IndexEntry, outDir: string): Promise<EssayJson | null> {
  try {
    const html = await fetchHtml(entry.url);
    const { essay, notesPageHref } = parseInlineEssay(entry.slug, entry.url, html);
    if (notesPageHref) {
      await sleep(DELAY_MS);
      const notesHtml = await fetchHtml(`${BASE}/${notesPageHref}`);
      essay.footnotes = parseNotesPage(notesHtml);
    }
    await writeFile(path.join(outDir, `${entry.slug}.json`), JSON.stringify(essay, null, 2));
    console.log(
      `ok ${entry.slug}: ${essay.paragraphs.length} paras, ${essay.footnotes.length} footnotes, ${essay.word_count} words`,
    );
    return essay;
  } catch (err) {
    console.warn(`SKIP ${entry.slug} (${entry.url}): ${(err as Error).message}`);
    return null;
  }
}

async function main() {
  const args = process.argv.slice(2);
  const slugsArg = args
    .find((a) => a.startsWith("--slugs"))
    ?.split("=")[1]
    ?.split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const limitArg = Number(args.find((a) => a.startsWith("--limit"))?.split("=")[1]);

  console.log(`fetching index ${INDEX_URL}`);
  const all = parseIndex(await fetchHtml(INDEX_URL));
  console.log(`index: ${all.length} essays`);

  let list = all;
  if (slugsArg?.length) {
    const set = new Set(slugsArg);
    list = all.filter((e) => set.has(e.slug));
    const missing = slugsArg.filter((s) => !set.has(s) || !list.some((e) => e.slug === s));
    if (missing.length) console.warn(`slugs not in index: ${missing.join(", ")}`);
  } else if (Number.isFinite(limitArg) && limitArg > 0) {
    list = all.slice(0, limitArg);
  }

  const outDir = path.join(process.cwd(), "data", "essays");
  await mkdir(outDir, { recursive: true });

  const index: EssayJson[] = [];
  const indexRows: { slug: string; title: string; date: string | null; word_count: number; reading_time_min: number }[] = [];
  for (let i = 0; i < list.length; i++) {
    const essay = await scrapeOne(list[i], outDir);
    if (essay) {
      index.push(essay);
      indexRows.push({
        slug: essay.slug,
        title: essay.title,
        date: essay.date,
        word_count: essay.word_count,
        reading_time_min: essay.reading_time_min,
      });
    }
    if (i < list.length - 1) await sleep(DELAY_MS);
  }

  await writeFile(path.join(process.cwd(), "data", "index.json"), JSON.stringify(indexRows, null, 2));
  console.log(`done: ${index.length}/${list.length} written. data/index.json updated.`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
