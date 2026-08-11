# catnews

> What's worth reading.

A curated digest of stories from **Hacker News**, **arXiv**, **GitHub**, and **Register Spill**, built with Python + FastAPI.

Sources are config-driven — anyone can host their own digest of any blog, newsletter,
or RSS feed by editing a single `sources.yaml` file.

**Live site:** [https://mkmlman.github.io/catnews/](https://mkmlman.github.io/catnews/)

## License

The code in this repository is released under the [MIT License](LICENSE) — do what you want with it.

The **curated content** it pulls in (newsletters, articles, papers, repos) remains
the property of its respective authors and sources; catnews merely links to and
quotes from it. See the [Sources](/sources/) page for what we curate.

```
 /\_/\
 (=^.^=)
 (")_(")
```

## Features

- **Single feed with filters** — every source's latest stories in one grid, filtered
  client-side by source (All / HN / arXiv / GitHub / Register Spill — chips are generated
  from `sources.yaml`).
  Each source is fetched on its own cadence and archived independently, so a weekly
  source (Register Spill) stays readable all week.
- **Archive** and **Stats** pages; the archive lists every snapshot and each
  date opens as a page (`/archive/<source>/<date>/`) in the same card layout as the home feed.
- **APIs**: JSON (`/api/sources`, `/api/sources/<source>`, `/api/sources/<source>/<date>`, `/api/digest`, `/api/stories`, `/api/search.json`, `/api/stats`), **Markdown** (`/api/stories.md`), and **RSS** (`/feed.rss`).
- **Curation** hooks to add *"Why read"* notes to stories.

## Quickstart

```sh
uv sync                                    # install deps
# optional: edit sources.yaml to add/remove/retune your sources
uv run python scripts/fetch_digest.py --all   # fetch every source -> data/source_<name>_<date>.json
uv run python scripts/build_site.py          # build the static site into site/
uv run uvicorn app.main:app --reload         # or serve live on http://localhost:8000
```

## Project layout

```
app/
  fetchers/        one module per built-in source (hn, arxiv, github)
                   + rss.py: generic fetcher for any blog/newsletter feed
                   (Substack, Ghost, ...)
  templates/       Jinja2 pages: base, index, archive, snapshot, stats
  static/          style.css + web fonts
  config.py        loads sources.yaml; palette + badge CSS generation; env overrides
  models.py        Story, SourceSnapshot, SiteStats, Digest (combined view)
  store.py         snapshot archive: load/save per-source data/source_*.json
  render.py        page/RSS/markdown rendering
  main.py          FastAPI dev server
scripts/
  fetch_digest.py  cadence-aware fetch (one snapshot per source)
  build_site.py    render a static site into site/
sources.yaml       source definitions — the single file a host edits
data/              source_<name>_<date>.json snapshots
.github/workflows/ deploy.yml (archive + lint + deploy to Pages)
```

## Adding a source

Sources live in `sources.yaml` (a built-in default is used if the file is absent). Any
blog or newsletter with a feed URL can be added as `type: rss` — no code changes needed.
Badges are assigned from the 12-color palette below, in source order; set `color:` to any
CSS color (e.g. `#2a5f8a`) to override a specific source.

```yaml
sources:
  - key: escflat
    label: Escaping Flatland
    tag: Henrik
    type: rss
    url: https://www.henrikkarlsson.xyz/feed
    cadence_days: 7
    limit: 10
```

Two optional rss-only fields make the generic fetcher cover newsletters like
Register Spill too — no custom code needed:

```yaml
  - key: registerspill
    label: Register Spill
    tag: Register Spill
    type: rss
    url: https://registerspill.thorstenball.com/feed
    url_filter: joy-and-curiosity   # keep only entries whose URL contains this
    extract_links: true             # show the links curated inside each post
    cadence_days: 7
    weekday: 0
```

Built-in sources (`hn`, `arxiv`, `github`) use `type: builtin` and have dedicated
JSON-API fetchers under `app/fetchers/`. `--source` and `--limit` in the CLI accept
any key from `sources.yaml`.

The 12 badge colors, in assignment order (source #1 → ember, #2 → clay, ...):

| # | Name | Hex | # | Name | Hex |
| --- | --- | --- | --- | --- | --- |
| 1 | ember | `#9c4d14` | 7 | plum | `#5b3e8a` |
| 2 | clay | `#8a1f18` | 8 | teal | `#1f6f6b` |
| 3 | graphite | `#3b3e37` | 9 | rose | `#8a2e4e` |
| 4 | cerulean | `#20507a` | 10 | steel | `#3f4f73` |
| 5 | moss | `#2e6b3e` | 11 | olive | `#6b5b1e` |
| 6 | amber | `#7a4a21` | 12 | bronze | `#6b3f1e` |

The palette lives in `PALETTE` in `app/config.py` (each entry also carries matching
light and dark theme background tints). Badges cycle back to ember for the 13th
source onward.

## How stories are selected

Each source is fetched independently and archived as its own snapshot
(`data/source_<name>_<date>.json`), driven by `app/fetchers/`. A source is only
re-fetched when its cadence has elapsed (`due_sources()` in `scripts/fetch_digest.py`):

| Source | Criteria | Cadence | Limit |
| --- | --- | --- | --- |
| **Hacker News** | Anything currently on the HN front page (`tags=front_page` via Algolia) | daily | 25 |
| **arXiv** | Latest papers in `cs.AI cs.CL cs.LG cs.SE cs.DB cs.CR cs.DC cs.NE`, sorted by submit date, newest first | weekly | 15 |
| **GitHub** | Repos created in the last 7 days, sorted by most stars (`search/repositories`) | daily | 15 |
| **Register Spill** | Joy & Curiosity series posts (Substack RSS, filtered by `joy-and-curiosity-` slug) | weekly, Mondays | 10 |

- A source that fails (network error, rate limit) is skipped — the others still produce snapshots.
- Register Spill has a preferred weekday (Monday): it is only fetched on Mondays, so the
  daily 07:00 UTC schedule lands its weekly snapshot on Monday morning and the section
  stays readable for the rest of the week.
- These are the *raw* pull rules; see **Curation** below to add "Why read" notes on top of them.

## Static site (GitHub Pages)

The site can be built as a fully static bundle and served for free from GitHub Pages at
`https://mkmlman.github.io/catnews/` — no server needed.

```sh
uv run python scripts/build_site.py --base-path /catnews --base-url https://mkmlman.github.io/catnews
```

The CI workflow derives `base-path` and `base-url` from the repository
(`/<repo>` and `https://<owner>.github.io/<repo>`), so a fork deploys to its own
Pages URL without editing the workflow.

This renders `site/` with plain HTML pages (home, archive, per-snapshot archive pages,
stats), `feed.rss`, and static JSON/Markdown API files (`api/sources.json`,
`api/stories.json`, `api/digest.json`, `api/stats.json`, `api/stories.md`). Preview it locally —
because the pages are built for the `/catnews` path, serve a folder that maps `/catnews` → `site/`:

```sh
mkdir -p preview && ln -sfn "$PWD/site" preview/catnews
uv run python -m http.server 8080 --directory preview
# then visit http://localhost:8080/catnews/
```

### Automatic daily updates

`.github/workflows/deploy.yml` runs on three triggers:

| Trigger | What happens |
| --- | --- |
| **Daily 07:00 UTC** (`schedule`) | `archive` fetches any source whose cadence is due, commits it to a `digest-*` branch, opens a PR, and auto-merges it into `main`; `lint` (ruff + ty) runs in parallel. `deploy` runs once `lint` passes and fetches its own data before building + publishing |
| **Push to `main`** | `archive` is skipped (data is already committed); `lint` (ruff + ty) then `deploy` — fetches, builds, publishes |
| **`workflow_dispatch`** | Full pipeline, same as the daily schedule |

Each run: `scripts/fetch_digest.py` pulls the due sources' stories into `data/` as
per-source snapshots, `scripts/build_site.py` renders `site/`, and `actions/deploy-pages`
publishes to GitHub Pages.

The `deploy` job's fetcher runs cadence-aware (nothing is downloaded for sources
fetched within their window), and the static build mirrors the main API endpoints
as files — e.g. `/api/sources` → `api/sources.json`. The dev server
(`uvicorn app.main:app`) additionally serves live routes like
`/api/sources/<source>/<date>` and `/archive/<source>/<date>/`.
The static build also emits compact per-source JSON files under `api/sources/` and
`api/search.json`, the deduplicated index used by archive search.

## Curation

To curate a day, create `data/curation_YYYY-MM-DD.json`:

```json
{
  "stories": {
    "hn:49138188": {
      "why_read": "A systematic approach to docs. Read this before writing your next one."
    }
  }
}
```

Keys are `"<source>:<external_id>"` (HN objectID, arXiv id, GitHub `owner/repo`) or the story URL. The fetch script applies overrides automatically.

## CLI

```sh
uv run python scripts/fetch_digest.py --help
```

```
usage: fetch_digest.py [-h] [--date DATE] [--no-curation] [--limit LIMIT]
                       [--source SOURCE] [--all] [--print]

options:
  --date DATE      Fetch date, YYYY-MM-DD
  --no-curation    Skip applying data/curation_YYYY-MM-DD.json overrides
  --limit LIMIT    Cap the number of stories per source (overrides config)
  --source SOURCE  Fetch only this source (any key from sources.yaml)
  --all            Fetch every source regardless of cadence
  --print          Print snapshots to stdout instead of saving
```

With no flags, only sources whose cadence is due are fetched — a source fetched
within the last `cadence_days` is skipped (e.g. Register Spill, cadence 7d, is
downloaded at most weekly).

## Tests

```sh
uv run pytest
```

Lint and type checks (also enforced in CI by the `lint` job, which gates deploys):

```sh
uv run ruff check .     # lints
uv run ruff format .    # auto-format (CI runs `--check`)
uv run ty check         # static type check
```

## Config

Sources are defined in `sources.yaml` (defaults in `app/config.py` if it's missing).
`cadence_days`, `limit`, and `weekday` can be overridden per-source there, and per-source
env vars remain available:

| Var | Default | Purpose |
| --- | --- | --- |
| `CATNEWS_BASE_URL` | `http://localhost:8000` | Canonical URL used in RSS links |
| `CATNEWS_DATA_DIR` | `./data` | Where snapshots live (`source_<name>_<date>.json`) |
| `CATNEWS_CADENCE_<KEY>` | per-source | Min days between fetches per source (uppercase key) |
| `CATNEWS_LIMIT_<KEY>` | per-source | Per-source story caps (uppercase key) |
| `CATNEWS_BASE_PATH` | `` (root) | URL prefix for the dev server (`` for localhost, `/catnews` for Pages) |
| `CATNEWS_FETCH_ATTEMPTS` | `3` | Attempts for transient fetch failures |
| `CATNEWS_FETCH_BACKOFF_SECONDS` | `1.0` | Initial exponential retry delay |

Register Spill is pinned to Mondays (`weekday: 0` in `sources.yaml`): it is only fetched
when at least 7 days have elapsed *and* it is Monday.

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
