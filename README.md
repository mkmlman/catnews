# catnews

> What's worth reading.

A curated digest of stories from **Hacker News**, **arXiv**, **GitHub**, **Register Spill**, and **Simon Willison**, built with Python + FastAPI.

Sources are config-driven — anyone can host their own digest of any blog, newsletter,
or RSS feed by editing a single `sources.yaml` file.

**Live site:** [https://mkmlman.github.io/catnews/](https://mkmlman.github.io/catnews/)

## License

The code in this repository is released under the [MIT License](LICENSE) — do what you want with it.

The **curated content** it pulls in (newsletters, articles, papers, repos) remains
the property of its respective authors and sources; catnews merely links to and
quotes from it. See the [Sources](https://mkmlman.github.io/catnews/sources/) page for what we curate.

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
- **Per-edition share cards** — every snapshot page has its own Open Graph image
  (`/static/og/<source>/<date>.png`) stamping the source color, date, and story count,
  generated at build time with no image dependencies.
- **Per-source RSS feeds** — `feed-<source>.rss` (e.g. `feed-hn.rss`, `feed-arxiv.rss`)
  in addition to the combined `feed.rss`, so readers can subscribe to just one section.
- **APIs**: JSON (`/api/sources`, `/api/sources/<source>`, `/api/digest`, `/api/stories`, `/api/search.json`, `/api/search-index.json` + per-year `api/search-YYYY.json`, `/api/stats`, `/api/trends.json`, `/api/fetch-status.json`, `/api/dead-links.json`), **Markdown** (`/api/stories.md`), and **RSS** (`/feed.rss`).
- **Link-rot checks** — `scripts/check_links.py` HEAD-checks every external story URL
  and a weekly workflow files a report issue when links have died. The same report
  is committed to `main`, and the site styles cards whose links are confirmed gone
  with a **"Dead link"** badge (so a rotted HN thread or withdrawn paper is obvious
  before you click it). Dead links also get a Wayback Machine rescue link.
- **Installable PWA** — generated 192px/512px/maskable icons, a manifest, and an
  app-shell service worker. The first-visit font set is preloaded without duplicates,
  and the day's pages stay browsable offline.
- **Curation** hooks to add *"Why read"* notes to stories.

## Quickstart

```sh
uv sync                                    # install deps
# optional: edit sources.yaml to add/remove/retune your sources
uv run python scripts/fetch_digest.py --all   # fetch every source -> data/source_<name>_<date>.json
uv run python scripts/build_site.py          # build the static site into site/
uv run catnews-dev                           # build + validate + preview at /catnews/
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
  check_site.py    validate a built site before publishing
  check_links.py   HEAD-check every archived URL (link rot)
  gen_og.py        regenerate the committed fallback share card (see below)
  dev.py           build + validate + serve a local preview
sources.yaml       source definitions — the single file a host edits
data/              source_<name>_<date>.json snapshots
.github/workflows/ deploy.yml (archive + lint + deploy to Pages) + linkcheck.yml (weekly link-rot report)
```

### The fallback share card

`app/static/og.png` is the brand-only card used as the `og:image` for pages that
don't have their own edition card (sources, stats, api, design, archive, 404) and
as the fallback for a missing per-edition card. It is the one raster in the repo
that the build does *not* generate, because it is not date- or source-specific.
Regenerate it after editing the wordmark or the paw mark in `app/og_image.py`:

```sh
uv run python scripts/gen_og.py
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
source onward. The share card's paw blobs read the same palette at draw time, so
re-tuning a color for contrast updates the card too.

## Source freshness

`fetch_status()` ages every source against its own `cadence_days`. The last successful
upstream check is tracked separately from the latest snapshot date, so a healthy feed
with no new stories is not repeatedly fetched or marked stale just because its content
did not change. A source becomes `stale` when it goes past its cadence without a
successful check — for example, if an upstream fails on the one weekday a weekly
source is allowed to fetch — and counts as an issue on the home banner and `/sources/`.
The last run's verdict alone is not enough: freshness must also account for how long
ago the last successful check happened.

Because an edition merges each source's *latest* stories rather than one day's
worth, the home hero names the **oldest** contributing snapshot (`since <date>`)
when it predates the edition date, so a digest built on a 3-week-old arXiv pull
doesn't claim to be entirely from today.

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

The build minifies the shipped `style.css`, `app.js`, and `fluid.js` in the output
directory only — `app/static/` stays the readable source, and `asset_version`
still fingerprints that source so the cache-busting query changes with it. Pass
`--no-minify` (also on `catnews-dev`) when you want to read the built files.
Minification is comment/whitespace removal only: string, template, and regex
literals are preserved byte-for-byte, which the test suite asserts.

The CI workflow derives `base-path` and `base-url` from the repository
(`/<repo>` and `https://<owner>.github.io/<repo>`), so a fork deploys to its own
Pages URL without editing the workflow.

This renders `site/` with plain HTML pages (home, archive, per-snapshot archive pages,
stats), `feed.rss` plus per-source `feed-<source>.rss` feeds, per-edition Open Graph
cards under `static/og/<source>/<date>.png`, and static JSON/Markdown API files
(`api/sources.json`, `api/stories.json`, `api/digest.json`, `api/stats.json`,
`api/fetch-status.json`, `api/dead-links.json`, `api/search.json`,
`api/search-index.json`, `api/stories.md`). The fetch-status
artifact records whether each source was current, stale, unavailable, or skipped on
the last fetch run; the dead-links artifact feeds the "Dead link" badges whenever
the weekly link-rot report is present under `data/linkcheck.json`.

For the shortest local feedback loop, use the build/validate/preview command:

```sh
uv run catnews-dev
# then visit http://127.0.0.1:8080/catnews/
```

The command builds the static artifact, validates all local references and required
files, then serves a temporary `/catnews` mount. To run the server manually instead,
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
| **Daily 07:00 UTC** (`schedule`) | `archive` fetches any source whose cadence is due, writes a fetch-status report, commits it to a `digest-*` branch, opens a PR, and auto-merges it into `main`; `lint` (ruff + ty + tests) runs in parallel. `deploy` runs once `lint` passes and fetches its own data before building, validating, and publishing |
| **Push to `main`** | `archive` is skipped (data is already committed); `lint` (ruff + ty + tests) then `deploy` — fetches, builds, validates, and publishes |
| **`workflow_dispatch`** | Full pipeline, same as the daily schedule |

Each run: `scripts/fetch_digest.py` pulls the due sources' stories into `data/` as
per-source snapshots, `scripts/build_site.py` renders `site/`, and `actions/deploy-pages`
publishes to GitHub Pages.

The `deploy` job's fetcher runs cadence-aware (nothing is downloaded for sources
fetched within their window), and the static build mirrors the main API endpoints
as files — e.g. `/api/sources` → `api/sources.json`. The dev server
(`uvicorn app.main:app`) additionally serves live routes like
`/api/sources/<source>/<date>` and `/archive/<source>/<date>/`.
The static build also emits compact per-source JSON files under `api/sources/`, the
deduplicated search index (`api/search.json` plus per-year shards and the
`api/search-index.json` directory), and `api/fetch-status.json` (the last
build-time source health report). The dev server serves the same shard routes, so the
browser's search loader behaves identically in both. Each deployment job has only the GitHub permissions it
needs: archive can write digests and PRs, lint can read the repository, and deploy can
publish Pages.

**Search index scaling:** `api/search.json` grows ~50 records/day. The build emits
per-year shards (`api/search-2026.json`) plus a tiny directory (`api/search-index.json`)
recording the shard list, the record count, the combined size, and the ~1 MB threshold.
The browser reads the directory on the first search and fetches either the one combined
index or all year shards in parallel; `api/search.json` stays the fallback for the dev
server and older builds, so search never breaks mid-migration. Note that
`api/stories.json` and `api/sources.json` are full-archive files (~1.2 MB each today
and growing), unlike the live server, which paginates `/api/stories` — prefer the
search index or the per-source endpoints for new integrations.

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
  --print          Print fetched snapshots to stdout (does not save snapshots or update fetch-status.json)
```

With no flags, only sources whose cadence is due are fetched — a source fetched
within the last `cadence_days` is skipped (e.g. Register Spill, cadence 7d, is
downloaded at most weekly).

## Tests

```sh
uv sync --extra dev
uv run playwright install chromium  # one-time setup for browser tests
uv run pytest
uv run python scripts/check_site.py --site site --base-path /catnews
```

The browser suite builds and serves a temporary static site, checks core filter,
search, theme, deep-link, and mobile-navigation flows at narrow viewport widths,
and runs axe-core against the main pages. CI installs Chromium and runs these
checks alongside the unit suite.

`check_site.py` also asserts what a reader can actually see: installable icon
sizes, the 192/512 install pair in `manifest.json`, that every search shard is
advertised in the directory, and that no local reference, canonical URL, or
`og:image` 404s.

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
| `CATNEWS_BASE_PATH` | `` (root) | URL prefix for the static Pages build (`` for localhost, `/catnews` for Pages); dev server always serves from `/` |
| `CATNEWS_REPO_URL` | `https://github.com/mkmlman/catnews` | Source link shown in the header/footer; set it so a fork points at its own repository |
| `CATNEWS_FETCH_ATTEMPTS` | `3` | Attempts for transient fetch failures |
| `CATNEWS_FETCH_BACKOFF_SECONDS` | `1.0` | Initial exponential retry delay |
| `CATNEWS_GITHUB_TOKEN` (`GITHUB_TOKEN` fallback) | `` (unauthenticated) | GitHub API token: 5000 req/hr instead of 60; set for reliable GitHub fetches |

Register Spill is pinned to Mondays (`weekday: 0` in `sources.yaml`): it is only fetched
when at least 7 days have elapsed *and* it is Monday.

## Link rot

An archive outlives its links: HN threads vanish, arXiv papers are withdrawn, and
repos are deleted. `scripts/check_links.py` HEAD-checks every external story URL in
the committed snapshots and reports which are dead:

```sh
uv run python scripts/check_links.py                      # summary on stdout
uv run python scripts/check_links.py --json linkcheck.json --report linkcheck.md
uv run python scripts/check_links.py --fail               # exit 1 if links are dead
```

It never fails a daily deploy on its own — a separate weekly workflow
(`.github/workflows/linkcheck.yml`) runs it, uploads the report as an artifact, and
opens a single "Link rot report" issue when dead links are found (so you prune a
retreating source without the site breaking silently). The workflow also commits the
machine-readable report to `data/linkcheck.json` (via a PR, like the digests), which
the next build turns into "Dead link" badges — 404/410/451 responses only, so a 403
bot-block is never branded dead while it is still serving people.

See [CONTRIBUTING.md](CONTRIBUTING.md) for repo ops (branch rules, PAT-less digest merges, workflow gotchas).
