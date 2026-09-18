# Ask Graham

A fast, distraction-free reader for [Paul Graham's essays](https://www.paulgraham.com/articles.html).

Read the whole catalog in one clean place — search it instantly, filter it by startup stage, pick up where you left off, and take any of it with you.

## Features

- **Full catalog** — 233 essays, grouped by year, newest first.
- **Reading paths** — a curated, ordered path through the essentials. Progress is saved and `j`/`k` move step by step.
- **Search** — `⌘K` / `Ctrl+K` or `/` for full-text search across every essay.
- **Filter by startup stage** — ideas, team, build, traction, growth, funding, running. Each essay opens with a one-line "Why read this".
- **Keyboard-first** — `j` / `k` moves between older and newer essays.
- **Reads well** — reading position is saved, text size and theme persist, footnotes preview inline.
- **Take it anywhere** — export every essay as markdown or JSON, sized for NotebookLM, Claude, ChatGPT, Gemini, Notion, and Obsidian.

## Getting started

```bash
pnpm install
pnpm dev
```

Open http://localhost:3000. The scraped essays and search index are committed, so it runs immediately; the export files are generated on startup.

## Scripts

| Command | Description |
| --- | --- |
| `pnpm dev` | Development server |
| `pnpm build` | Production build (refreshes the search index and exports first) |
| `pnpm lint` | ESLint |
| `pnpm scrape` | Re-scrape the essay catalog into `data/` |
| `pnpm index:search` | Rebuild the browser search index |
| `pnpm export:corpus` | Rebuild the markdown and JSON exports |
| `pnpm classify` | Tag essays by startup stage (needs an OpenRouter key) |
| `pnpm paths` | Curate reading paths from the catalog (needs an OpenRouter key) |

## Updating data

- **Essays** — `pnpm scrape` follows paulgraham.com and writes `data/essays/<slug>.json` plus `data/index.json`.
- **Stage tags** — `pnpm classify` asks an LLM which stages each essay helps and writes `data/phases.json`. Copy `.env.example` to `.env` and add an `OPENROUTER_API_KEY` first. Results are cached by essay content, so re-runs only pay for new or edited essays.
- **Reading paths** — edit the intents in `data/paths.spec.json`, then run `pnpm paths` to generate `data/paths.json`. Cached per path, so `pnpm paths -- --only=start-here --force` regenerates just one.

Both are one-off authoring steps; the generated files are committed, so the app never needs an API key at runtime.

## Project structure

```
app/          Pages, metadata, sitemap, robots, Open Graph image
components/   Reader, reading paths, search palette, stage filter, theme, icons
lib/          Data access, paths, stage tags, dates, SEO helpers
scripts/      Scrape, search index, exports, stage classifier, path curator
data/         Scraped essays, index, taxonomy, stage tags, reading paths
public/       Generated search index and corpus exports
```

## Credits

All essays are by [Paul Graham](https://www.paulgraham.com) and remain his. This is a personal reading tool that links back to the originals.
