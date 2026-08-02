# catnews — The Daily Cat

A [](https:///)-style curated digest of stories from **Hacker News**, **arXiv**, and **GitHub**, built with Python + FastAPI.

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
uv run uvicorn app.main:app --reload    # serve on http://localhost:8000
```

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
