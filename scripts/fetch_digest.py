from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR, DIGEST_LIMITS, REQUEST_TIMEOUT, USER_AGENT
from app.fetchers.arxiv import fetch_arxiv
from app.fetchers.github import fetch_github
from app.fetchers.hn import fetch_hn
from app.models import Digest, Story

FETCHERS = {"hn": fetch_hn, "arxiv": fetch_arxiv, "github": fetch_github}


def load_curation(day: date, data_dir: Path) -> dict:
    """Load optional curation overrides from data/curation_YYYY-MM-DD.json.

    Shape: {"stories": {"<source>:<external_id>": {"signal": "Must-Read", "why_read": "..."}}}
    """
    path = data_dir / f"curation_{day.isoformat()}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data.get("stories", {})
    except (json.JSONDecodeError, OSError):
        print(f"[catnews] warning: could not parse curation file {path}")
        return {}


def apply_curation(stories: list[Story], curation: dict) -> list[Story]:
    for story in stories:
        key = f"{story.source}:{story.external_id}" if story.external_id else story.url
        overrides = curation.get(key) or curation.get(story.url)
        if not overrides:
            continue
        if "signal" in overrides:
            story.signal = overrides["signal"]
        if "why_read" in overrides:
            story.why_read = overrides["why_read"]
        if "summary" in overrides:
            story.summary = overrides["summary"]
    return stories


def interleave(stories_by_source: dict[str, list[Story]]) -> list[Story]:
    """Round-robin across sources so the digest mixes HN, arXiv, and GitHub."""
    result: list[Story] = []
    queues = {k: list(v) for k, v in stories_by_source.items()}
    while any(queues.values()):
        for source in queues:
            if queues[source]:
                result.append(queues[source].pop(0))
    return result


async def build(day: date, data_dir: Path, limits: dict[str, int], apply_curation_file: bool) -> Digest:
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT) as client:
        by_source: dict[str, list[Story]] = {}
        for source, fn in FETCHERS.items():
            try:
                by_source[source] = (await fn(client))[: limits.get(source, 50)]
            except Exception as exc:  # noqa: BLE001 - one source failing shouldn't kill the digest
                print(f"[catnews] {source} fetch failed: {exc}")
                by_source[source] = []
    stories = interleave(by_source)
    if apply_curation_file:
        stories = apply_curation(stories, load_curation(day, data_dir))
    return Digest(date=day, stories=stories)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a day's digest for catnews.")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="Digest date, YYYY-MM-DD")
    parser.add_argument(
        "--no-curation",
        action="store_true",
        help="Skip applying data/curation_YYYY-MM-DD.json overrides",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of stories per source (overrides config)",
    )
    parser.add_argument("--print", action="store_true", help="Print the digest to stdout instead of saving")
    args = parser.parse_args()

    limits = {k: (args.limit or v) for k, v in DIGEST_LIMITS.items()}
    digest = asyncio.run(build(args.date, DATA_DIR, limits, apply_curation_file=not args.no_curation))

    if args.print:
        print(digest.model_dump_json(indent=2))
        return

    path = save_digest(digest, DATA_DIR)
    print(f"[catnews] saved {len(digest.stories)} stories to {path}")
    for source, count in digest.stats.items():
        print(f"  {source:<6} {count}")


from app.store import save_digest  # noqa: E402


if __name__ == "__main__":
    main()
