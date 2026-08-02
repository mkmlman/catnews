# catnews — The Daily Cat

A curated digest of stories from **Hacker News**, **arXiv**, and **GitHub**, built with Python + FastAPI.

```
 /\_/\
 (=^.^=)
 (")_(")
```

## Features

- **Daily digest** of top HN front-page stories, fresh arXiv cs papers, and popular new GitHub repos.
- **Client-side filtering** by source (All / HN / arXiv / GitHub) and signal (All / Recommended / Must-Read).
- **Archive** and **Stats** pages.
- **APIs**: JSON (`/api/digest`, `/api/stories`, `/api/stats`), **Markdown** (`/api/stories.md`), and **RSS** (`/feed.rss`).
- **Curation** hooks to mark stories as *Recommended* / *Must-Read* and add *"Why read"* notes.

## Quickstart

```sh
uv sync                       # install deps
uv run python scripts/fetch_digest.py   # build today's digest -> data/digest_YYYY-MM-DD.json
uv run uvicorn app.main:app --reload    # serve on http://localhost:8000 (dev server)
```

## Static site (GitHub Pages)

The site can be built as a fully static bundle and served for free from GitHub Pages at
`https://mkmlman.github.io/catnews/` — no server needed.

```sh
uv run python scripts/build_site.py --base-path /catnews --base-url https://mkmlman.github.io/catnews
```

This renders `site/` with plain HTML pages, `feed.rss`, and static JSON/Markdown API files
(`api/digest.json`, `api/stories.json`, `api/stories.md`, ...). Preview it locally:

```sh
uv run python -m http.server 8080 --directory site
# then visit http://localhost:8080/catnews/
```

### Automatic daily updates

`.github/workflows/deploy.yml` runs every day at 07:00 UTC (and on `workflow_dispatch`):

1. `scripts/fetch_digest.py` pulls the day's stories and commits `data/digest_YYYY-MM-DD.json`.
2. `scripts/build_site.py` rebuilds the static site.
3. `actions/deploy-pages` publishes it to GitHub Pages.

The JSON "API" endpoints become static files, so links change accordingly, e.g.
`/api/digest` → `/api/digest.json` and `/api/digest/{date}` → `/api/digest_{date}.json`.

## Curation

To curate a day, create `data/curation_YYYY-MM-DD.json`:

```json
{
  "stories": {
    "hn:49138188": {
      "signal": "Must-Read",
      "why_read": "A systematic approach to docs. Read this before writing your next one."
    }
  }
}
```

Keys are `"<source>:<external_id>"` (HN objectID, arXiv id, GitHub `owner/repo`) or the story URL. The fetch script applies overrides automatically.

## CLI

```
usage: catnews-fetch [-h] [--date YYYY-MM-DD] [--no-curation] [--limit N] [--print]

positional arguments:
  --date        digest date (default: today)
  --no-curation skip applying curation overrides
  --limit N     cap stories per source
  --print       print JSON instead of saving
```

## Tests

```sh
uv run pytest
```

## Config (env vars)

| Var | Default | Purpose |
| --- | --- | --- |
| `CATNEWS_BASE_URL` | `http://localhost:8000` | Canonical URL used in RSS links |
| `CATNEWS_DATA_DIR` | `./data` | Where digest JSON lives |
| `CATNEWS_LIMIT_HN` / `_ARXIV` / `_GITHUB` | 25 / 15 / 15 | Per-source digest caps |
