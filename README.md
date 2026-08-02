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

## How stories are selected

Every digest is pulled fresh from three sources (`app/fetchers/`), each capped by
`CATNEWS_LIMIT_*`, then round-robin interleaved so the edition mixes all three:

| Source | Criteria | Requested | Kept |
| --- | --- | --- | --- |
| **Hacker News** | Anything currently on the HN front page (`tags=front_page` via Algolia) | 60 | 25 |
| **arXiv** | Latest papers in `cs.AI cs.CL cs.LG cs.SE cs.DB cs.CR cs.DC cs.NE`, sorted by submit date, newest first | 40 | 15 |
| **GitHub** | Repos created in the last 7 days, sorted by most stars (`search/repositories`) | 40 | 15 |

- A source that fails (network error, rate limit) is skipped — the other sources still
  produce the digest.
- These are the *raw* pull rules; see **Curation** below to promote stories to
  *Recommended* / *Must-Read* and add "Why read" notes on top of them.

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

`.github/workflows/deploy.yml` runs on three triggers:

| Trigger | What happens |
| --- | --- |
| **Daily 07:00 UTC** (`schedule`) | `archive` job fetches today's digest, commits it to a `digest-*` branch, opens a PR, and auto-merges it into `main`; then `deploy` job builds + publishes |
| **Push to `main`** | `deploy` job only — fetches, builds, publishes (the digest is already committed by the PR merge) |
| **`workflow_dispatch`** | Full pipeline, same as the daily schedule |

Each run: `scripts/fetch_digest.py` pulls the day's stories into `data/`,
`scripts/build_site.py` renders `site/`, and `actions/deploy-pages` publishes
to GitHub Pages.

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

## Repo ops (how GitHub is configured)

Public repo, only the owner (`mkmlman`) has write access; everyone else can only
clone, fork, and open PRs.

**Branch ruleset — "protect main"** (Settings → Rules, or REST):
- `main` requires changes to come through a PR; branch deletion and force-push are blocked.
- Owner (admin role) bypasses everything; the GitHub Actions bot does **not** bypass —
  PR merges are used instead so no token is needed.

**Key gotchas learned:**
- `GITHUB_TOKEN` cannot push to a PR-protected branch on a personal repo, and it
  cannot be added to a ruleset bypass list. To archive digests automatically, the
  workflow pushes to a `digest-*` branch and `gh pr merge --squash` it — a PR merge
  satisfies the "changes via PR" rule, so no PAT is required.
- The `gh` CLI in workflows needs `env: GH_TOKEN: ${{ github.token }}`.
- "Allow GitHub Actions to create and approve pull requests" (Settings → Actions →
  General → Workflow permissions) is **off by default** for personal repos and must
  be enabled, or the bot's PR creation fails with
  `GitHub Actions is not permitted to create or approve pull requests`.
- The workflow commit step is gated with `if: github.event_name != 'push'` so the
  PR merge's own push-triggered run doesn't re-commit (prevents infinite loops).
- Wiki is disabled; Issues and forking remain enabled.
