# Ask Graham

A fast, distraction-free reader for [Paul Graham's essays](https://www.paulgraham.com/articles.html).

**Live:** https://askgraham.vercel.app/

The full catalog is scraped to local JSON, rendered as static pages, and searchable entirely in the browser — no database, no server, no tracking.

## Features

- **Full catalog** — 233 essays bundled as structured JSON, grouped by year and sorted newest first.
- **Full-text search** — `⌘K` / `Ctrl+K` or `/` opens a command palette powered by a client-side [FlexSearch](https://github.com/nextapps-de/flexsearch) index built at build time. Title matches rank above in-text matches.
- **Keyboard-first reading** — `j` / `k` move to the older / newer essay; arrow keys navigate search results.
- **Persistent reading position** — scroll position is saved per essay and restored on return.
- **Reader preferences** — text size (A− / A / A+) and theme (system / light / dark) persist in `localStorage`, with a no-flash theme boot script.
- **Inline footnotes** — hover, focus, or tap a `[n]` reference to preview the note; full notes are listed below the article.
- **Clean typography** — Georgia serif body at a 70ch measure, dark mode throughout.

## Stack

- [Next.js](https://nextjs.org) 16 (App Router) + React 19, statically generated
- TypeScript, Tailwind CSS v4
- [FlexSearch](https://github.com/nextapps-de/flexsearch) for browser-side search
- [Cheerio](https://cheerio.js.org) + [tsx](https://tsx.is) for the scrape/index build scripts
- pnpm · deployed on [Vercel](https://vercel.com)

## Getting started

```bash
pnpm install
pnpm dev
```

Open http://localhost:3000.

> The repo ships with the scraped essays and generated search index, so the app runs immediately. Re-run the scripts below only if you want to refresh the data.

## Scripts

| Command | Description |
| --- | --- |
| `pnpm dev` | Start the dev server |
| `pnpm build` | Build for production (runs `index:search` first via `prebuild`) |
| `pnpm start` | Serve the production build |
| `pnpm lint` | Run ESLint |
| `pnpm scrape` | Scrape the full Paul Graham catalog into `data/` |
| `pnpm scrape:sample` | Scrape a small sample (`say`, `ramenprofitable`, `foundermode`) |
| `pnpm index:search` | Rebuild the FlexSearch index in `public/search-index/` |

### Scraping

`scripts/scrape-essays.ts` follows the essay index on paulgraham.com, extracts each essay's title, date, body paragraphs, and footnotes (including separate `*notes.html` pages), then writes:

- `data/essays/<slug>.json` — one file per essay
- `data/index.json` — the catalog index used by the app

It rate-limits requests and handles the site's legacy quirks (Windows-1252 encoding, loose `<p>` markup, in-body ad tables, year-only dates). Options:

```bash
pnpm scrape -- --limit 5
pnpm scrape -- --slugs say,ramenprofitable,foundermode
```

### Search index

`scripts/build-search-index.ts` reads every essay and exports a serialized FlexSearch `Document` plus metadata to `public/search-index/`. The palette lazy-loads these files on first search. The index options in the script and in `components/search-palette.tsx` must stay in sync.

## Project structure

```
app/
  page.tsx                 Essay catalog, grouped by year
  essays/[slug]/page.tsx   Statically generated essay reader
  api/chat/route.ts        Stub for a future RAG chat feature (501)
  layout.tsx               Header, footer, theme boot script
components/
  essay-reader.tsx         Article rendering, footnotes, j/k nav, progress
  search-palette.tsx       ⌘K command palette
  theme-toggle.tsx         Theme switcher
  reader-prefs.ts          localStorage-backed preferences
lib/essays.ts              Data access + canonical ordering
scripts/
  scrape-essays.ts         Catalog scraper
  build-search-index.ts    FlexSearch index builder
data/                      Scraped essays + index (committed)
public/search-index/       Generated search index (committed)
```

## Roadmap

`app/api/chat/route.ts` is a placeholder for an "ask the essays" chat feature — RAG over the local essay corpus. It currently returns `501 Not Implemented`.

## Notes

Personal learning project. All essays are by [Paul Graham](https://www.paulgraham.com) and remain his property; this tool only provides an alternate reading experience and links back to the originals.
