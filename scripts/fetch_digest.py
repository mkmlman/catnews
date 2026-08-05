from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR, REQUEST_TIMEOUT, SOURCES, USER_AGENT, today_utc
from app.fetchers import get_fetcher
from app.models import SourceSnapshot, Story
from app.store import last_fetched, save_snapshot


def load_curation(day: date, data_dir: Path) -> dict:
    """Load optional curation overrides from data/curation_YYYY-MM-DD.json.

    Shape: {"stories": {"<source>:<external_id>": {"why_read": "...", "summary": "..."}}}
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
        if "why_read" in overrides:
            story.why_read = overrides["why_read"]
        if "summary" in overrides:
            story.summary = overrides["summary"]
    return stories


async def fetch_one(
    client, source: str, limit: int, day: date, data_dir: Path
) -> SourceSnapshot:
    fn = get_fetcher(SOURCES[source])
    stories = (await fn(client))[:limit]
    stories = apply_curation(stories, load_curation(day, data_dir))
    return SourceSnapshot(source=source, date=day, stories=stories)


async def build(
    day: date, data_dir: Path, sources: list[str], limits: dict[str, int]
) -> list[SourceSnapshot]:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
    ) as client:
        results = await asyncio.gather(
            *(
                fetch_one(client, source, limits[source], day, data_dir)
                for source in sources
            ),
            return_exceptions=True,
        )
    snapshots: list[SourceSnapshot] = []
    for source, result in zip(sources, results):
        if isinstance(result, BaseException):
            print(f"[catnews] {source} fetch failed: {result}")
            continue
        snapshots.append(result)
    return snapshots


def due_sources(day: date, data_dir: Path, force: bool = False) -> list[str]:
    """Sources that haven't been fetched within their cadence (or any if force)."""
    if force:
        return list(SOURCES)
    due: list[str] = []
    for source, meta in SOURCES.items():
        last = last_fetched(source, data_dir)
        if last is None:
            due.append(source)
            continue
        elapsed = (day - last).days
        if elapsed < meta["cadence_days"]:
            continue
        # Sources with a preferred weekday (e.g. Register Spill on Mondays)
        # only run on that weekday, otherwise they'd drift off schedule.
        weekday = meta.get("weekday")
        if weekday is not None and day.weekday() != weekday:
            continue
        due.append(source)
    return due


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch per-source digests for catnews."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=today_utc(),
        help="Fetch date, YYYY-MM-DD",
    )
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
    parser.add_argument(
        "--source", default=None, help="Fetch only this source (e.g. hn, registerspill)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch every source regardless of cadence",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print snapshots to stdout instead of saving",
    )
    args = parser.parse_args()

    if args.source and args.source not in SOURCES:
        raise SystemExit(f"Unknown source {args.source!r}. Known: {', '.join(SOURCES)}")

    sources = (
        [args.source]
        if args.source
        else due_sources(args.date, DATA_DIR, force=args.all)
    )
    if not sources:
        print("[catnews] no sources due today; nothing to fetch.")
        return

    limits = {source: (args.limit or SOURCES[source]["limit"]) for source in sources}
    snapshots = asyncio.run(build(args.date, DATA_DIR, sources, limits))

    if args.print:
        print(json.dumps([s.model_dump(mode="json") for s in snapshots], indent=2))
        return

    for snap in snapshots:
        path = save_snapshot(snap, DATA_DIR)
        print(f"[catnews] saved {snap.source}: {len(snap.stories)} stories -> {path}")


if __name__ == "__main__":
    main()
