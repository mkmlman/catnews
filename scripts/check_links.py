"""External link-rot check for the deployed catnews site.

The archive lives longer than the URLs it points to (HN threads, arXiv papers,
and GitHub repos get removed over time). This script HEAD-checks every external
link in the site's story data and reports which ones are dead, so a maintainer
can prune retreating sources without a stalled site breaking silently.

Designed to run on a schedule (see .github/workflows/linkcheck.yml): it never
fails the pipeline on its own — dead links are reported, not fatal. Pass
``--fail`` to exit non-zero when dead links are found.

Usage::

    uv run python scripts/check_links.py
    uv run python scripts/check_links.py --site site --json linkcheck.json --report linkcheck.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR, REQUEST_TIMEOUT, USER_AGENT

MAX_WORKERS = 8
RETRIES = 2
BACKOFF = 1.0


def collect_story_urls(stories: list[dict]) -> list[dict]:
    """Flatten a story to the unique external URLs worth checking.

    Returns one record per URL with provenance (source, title, url) so a report
    can say which story lost a link.
    """
    seen: set[str] = set()
    records: list[dict] = []
    for story in stories:
        candidates = [story.get("url"), story.get("hn_url")]
        for link in story.get("links", []) or []:
            candidates.append(link.get("url"))
        for url in candidates:
            if not url:
                continue
            if url in seen:
                continue
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            seen.add(url)
            records.append(
                {
                    "url": url,
                    "source": story.get("source", "?"),
                    "title": story.get("title", url),
                    "domain": parsed.netloc.lower(),
                }
            )
    return records


def classify_status(status: int | None) -> str:
    """Map an HTTP status to dead | good | error."""
    if status is None:
        return "error"
    if status in (404, 410, 451):
        return "dead"
    if 400 <= status < 500:
        return "dead"
    if status >= 500:
        return "error"
    return "good"


def check_url(client: httpx.Client, record: dict) -> dict:
    """HEAD-check one URL, retrying transient failures."""
    url = record["url"]
    last_status: int | None = None
    error: str | None = None
    for attempt in range(RETRIES + 1):
        try:
            response = client.head(url)
            if response.status_code == 405:
                response = client.get(url, follow_redirects=True)
            response.raise_for_status()
            return {**record, "status": response.status_code, "error": None}
        except httpx.HTTPStatusError as exc:
            last_status = exc.response.status_code
            if last_status not in (None, 404, 410, 451) and (
                last_status >= 400 and last_status < 500
            ):
                break
            if last_status in (404, 410, 451):
                break
            if attempt < RETRIES:
                time.sleep(BACKOFF * (attempt + 1))
                continue
        except httpx.HTTPError as exc:
            error = type(exc).__name__
            if attempt < RETRIES:
                time.sleep(BACKOFF * (attempt + 1))
                continue
    return {**record, "status": last_status, "error": error}


def check_links(
    stories: list[dict],
    *,
    max_urls: int = 0,
    concurrency: int = MAX_WORKERS,
) -> list[dict]:
    """Check every external story URL; returns one result dict per URL."""
    records = collect_story_urls(stories)
    if max_urls:
        records = records[:max_urls]

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    }
    results: list[dict] = []
    with (
        ThreadPoolExecutor(max_workers=concurrency) as pool,
        httpx.Client(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=headers,
            limits=httpx.Limits(
                max_connections=concurrency, max_keepalive_connections=concurrency
            ),
        ) as client,
    ):
        futures = {pool.submit(check_url, client, rec): rec["url"] for rec in records}
        for future in as_completed(futures):
            result = future.result()
            result["state"] = classify_status(result.get("status"))
            results.append(result)
    results.sort(key=lambda r: (r["state"], r["domain"]))
    return results


def summarize(results: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for result in results:
        counts[result["state"]] = counts.get(result["state"], 0) + 1
    return counts


def render_markdown_report(results: list[dict]) -> str:
    lines = [
        "# Link rot report",
        "",
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
    ]
    counts = summarize(results)
    lines.append(
        f"**Checked:** {len(results)} links "
        f"({counts.get('good', 0)} ok, {counts.get('dead', 0)} dead, "
        f"{counts.get('error', 0)} unchecked)."
    )
    lines.append("")
    dead = [r for r in results if r["state"] == "dead"]
    if dead:
        lines.append(f"## Dead links ({len(dead)})")
        lines.append("")
        for r in dead:
            lines.append(
                f"- [{r['title']}]({r['url']}) — *{r['source']}* "
                f"(HTTP {r.get('status')})"
            )
    errors = [r for r in results if r["state"] == "error"]
    if errors:
        lines.append("")
        lines.append(f"## Could not verify ({len(errors)})")
        lines.append("")
        for r in errors:
            detail = r.get("error") or f"HTTP {r.get('status')}"
            lines.append(f"- {r['url']} — {detail}")
    if not dead and not errors:
        lines.append("No dead or unverified links. 🎉")
    lines.append("")
    lines.append("*Manual check recommended for anything listed above.*")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check external links in the catnews story archive."
    )
    parser.add_argument(
        "--site",
        type=Path,
        default=None,
        help="Built site dir; reads site/api/stories.json when given (default: data snapshots)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="Snapshot dir used when --site is not given (default: ./data)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=0,
        help="Cap the number of URLs checked this run (0 = all)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        dest="json_out",
        help="Write a machine-readable JSON report to this path",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write a human-readable markdown report to this path",
    )
    parser.add_argument(
        "--fail",
        action="store_true",
        help="Exit non-zero when dead or unverified links are found",
    )
    args = parser.parse_args()

    if args.site is not None:
        stories_path = args.site / "api" / "stories.json"
        stories = json.loads(stories_path.read_text(encoding="utf-8"))
    else:
        stories = []
        for path in sorted((args.data_dir or DATA_DIR).glob("source_*_*.json")):
            stories.extend(json.loads(path.read_text(encoding="utf-8"))["stories"])

    results = check_links(stories, max_urls=args.max)
    counts = summarize(results)
    print(
        f"[catnews] checked {len(results)} links: "
        f"{counts.get('good', 0)} ok, {counts.get('dead', 0)} dead, "
        f"{counts.get('error', 0)} unverified "
        f"(from {len(stories)} stories)"
    )
    for result in results:
        if result["state"] != "good":
            detail = result.get("error") or f"HTTP {result.get('status')}"
            print(f"  [{result['state']}] {result['url']} ({detail})")

    if args.json_out:
        report = {
            "generated": datetime.now(UTC).isoformat(),
            "summary": counts,
            "checked": len(results),
            "results": results,
        }
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    if args.report:
        args.report.write_text(render_markdown_report(results))
        print(f"[catnews] markdown report -> {args.report}")

    dead = counts.get("dead", 0)
    if args.fail and (dead or counts.get("error", 0)):
        raise SystemExit(f"[catnews] link check failed: {dead} dead links")
    print(f"dead={dead} error={counts.get('error', 0)}")


if __name__ == "__main__":
    main()
