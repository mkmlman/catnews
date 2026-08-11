from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from .config import SOURCES, cadence_label, today_utc
from .models import Digest, SiteStats, SourceSnapshot, Story


def _snapshot_parts(path: Path) -> tuple[str, date] | None:
    """Extract a source key and date from a snapshot filename."""
    stem = path.stem
    if not stem.startswith("source_"):
        return None
    source, separator, raw_date = stem.removeprefix("source_").rpartition("_")
    if not separator or not source:
        return None
    try:
        return source, date.fromisoformat(raw_date)
    except ValueError:
        return None


def snapshot_path(source: str, date_obj: date, data_dir: Path) -> Path:
    return data_dir / f"source_{source}_{date_obj.isoformat()}.json"


def list_snapshot_dates(source: str, data_dir: Path) -> list[date]:
    dates: list[date] = []
    for path in data_dir.glob(f"source_{source}_*.json"):
        parts = _snapshot_parts(path)
        if parts and parts[0] == source:
            dates.append(parts[1])
    return sorted(dates)


def load_snapshot(source: str, date_obj: date, data_dir: Path) -> SourceSnapshot | None:
    path = snapshot_path(source, date_obj, data_dir)
    if not path.exists():
        return None
    return SourceSnapshot.model_validate_json(path.read_text())


def load_latest_snapshot(source: str, data_dir: Path) -> SourceSnapshot | None:
    dates = list_snapshot_dates(source, data_dir)
    if not dates:
        return None
    return load_snapshot(source, dates[-1], data_dir)


def last_fetched(source: str, data_dir: Path) -> date | None:
    dates = list_snapshot_dates(source, data_dir)
    return dates[-1] if dates else None


def save_snapshot(snapshot: SourceSnapshot, data_dir: Path) -> Path:
    path = snapshot_path(snapshot.source, snapshot.date, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=data_dir,
            prefix=f".{path.name}.",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(snapshot.model_dump_json(indent=2))
        temp_path.replace(path)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
    return path


def load_all_snapshots(data_dir: Path) -> list[SourceSnapshot]:
    sources = sorted(
        {
            parts[0]
            for path in data_dir.glob("source_*_*.json")
            if (parts := _snapshot_parts(path))
        }
    )
    snapshots: list[SourceSnapshot] = []
    for source in sources:
        for date_obj in list_snapshot_dates(source, data_dir):
            snap = load_snapshot(source, date_obj, data_dir)
            if snap:
                snapshots.append(snap)
    return snapshots


def latest_stories_by_source(data_dir: Path) -> dict[str, list[Story]]:
    """Latest fetch of every source that has been archived."""
    return {
        s.source: s.stories
        for s in (load_latest_snapshot(s, data_dir) for s in sorted(_sources(data_dir)))
        if s
    }


def _sources(data_dir: Path) -> list[str]:
    return sorted(
        {
            parts[0]
            for path in data_dir.glob("source_*_*.json")
            if (parts := _snapshot_parts(path))
        }
    )


def combined_digest(data_dir: Path, day: date | None = None) -> Digest | None:
    """A Digest combining the latest stories from every source (for RSS/markdown).

    Sources are interleaved round-robin so one source (e.g. a large HN pull)
    doesn't dominate the top of the feed.
    """
    per_source: list[list[Story]] = []
    for source in SOURCES:
        snap = load_latest_snapshot(source, data_dir)
        if snap:
            per_source.append(snap.stories)
    stories = interleave(per_source)
    if not stories:
        return None
    return Digest(date=day or today_utc(), stories=stories)


def interleave(groups: list[list[Story]]) -> list[Story]:
    """Round-robin across groups so every group appears early in the result."""
    result: list[Story] = []
    remaining = [list(g) for g in groups if g]
    while remaining:
        still_going: list[list[Story]] = []
        for group in remaining:
            result.append(group.pop(0))
            if group:
                still_going.append(group)
        remaining = still_going
    return result


def source_registry(data_dir: Path) -> list[dict]:
    """Registry rows for the Sources page: config plus latest snapshot info."""
    rows: list[dict] = []
    for key, cfg in SOURCES.items():
        snap = load_latest_snapshot(key, data_dir)
        rows.append(
            {
                "key": key,
                "label": cfg["label"],
                "tag": cfg["tag"],
                "cadence": cadence_label(key),
                "limit": cfg.get("limit"),
                "last_fetched": snap.date if snap else None,
                "stories": len(snap.stories) if snap else 0,
            }
        )
    return rows


def site_stats(data_dir: Path) -> SiteStats:
    snapshots = load_all_snapshots(data_dir)
    total = 0
    by_source: dict[str, int] = {}
    snapshots_by_source: dict[str, int] = {}
    for snap in snapshots:
        snapshots_by_source[snap.source] = snapshots_by_source.get(snap.source, 0) + 1
        for story in snap.stories:
            total += 1
            by_source[story.source] = by_source.get(story.source, 0) + 1
    dates = [s.date for s in snapshots]
    return SiteStats(
        total_stories=total,
        editions=len(snapshots),
        first_edition=min(dates) if dates else None,
        last_edition=max(dates) if dates else None,
        by_source=dict(sorted(by_source.items())),
        snapshots_by_source=dict(sorted(snapshots_by_source.items())),
    )


def weekly_trends(data_dir: Path) -> list[dict]:
    """Story counts by source per ISO week, for the stats trends table.

    Returns a list of dicts (oldest first):
      {"week": "2026-W32", "start": date, "end": date,
       "counts": {"hn": 25, ...}, "total": 27}
    """
    from collections import defaultdict

    buckets: dict[tuple[int, int], dict] = {}
    for snap in load_all_snapshots(data_dir):
        iso = snap.date.isocalendar()
        key = (iso.year, iso.week)
        bucket = buckets.setdefault(key, {"counts": defaultdict(int), "dates": set()})
        bucket["dates"].add(snap.date)
        for story in snap.stories:
            bucket["counts"][story.source] += 1
    rows: list[dict] = []
    for (year, week_num), bucket in sorted(buckets.items()):
        counts = dict(sorted(bucket["counts"].items()))
        rows.append(
            {
                "week": f"{year}-W{week_num:02d}",
                "start": min(bucket["dates"]),
                "end": max(bucket["dates"]),
                "counts": counts,
                "total": sum(counts.values()),
            }
        )
    return rows


def top_domains(data_dir: Path, limit: int = 10) -> list[tuple[str, int]]:
    """Most common story URL hostnames across all archived snapshots."""
    from collections import Counter
    from urllib.parse import urlparse

    counter: Counter[str] = Counter()
    for snap in load_all_snapshots(data_dir):
        for story in snap.stories:
            host = urlparse(story.url).netloc
            host = host.removeprefix("www.")
            if host:
                counter[host] += 1
    return counter.most_common(limit)


def arxiv_category_counts(data_dir: Path) -> list[tuple[str, int]]:
    """Most common arXiv primary categories across archived arXiv stories."""
    from collections import Counter

    counter: Counter[str] = Counter()
    for snap in load_all_snapshots(data_dir):
        for story in snap.stories:
            if story.category:
                counter[story.category] += 1
    return counter.most_common()


def days_archiving(data_dir: Path) -> int:
    """Number of calendar days spanned by the archive (1 if a single day)."""
    dates = [s.date for s in load_all_snapshots(data_dir)]
    if not dates:
        return 0
    return (max(dates) - min(dates)).days + 1


def fetch_health(data_dir: Path) -> list[dict]:
    """Per-source fetch success: actual snapshots vs expected by cadence.

    Expected count = number of fetch dates the source's cadence implies,
    anchored at the source's own first snapshot and spanning through the
    most recent archive date.
    """
    from datetime import timedelta

    from .config import SOURCES

    snapshots = load_all_snapshots(data_dir)
    if not snapshots:
        return []
    by_source: dict[str, list] = {}
    for snap in snapshots:
        by_source.setdefault(snap.source, []).append(snap.date)

    last_archive = max(s.date for s in snapshots)
    rows: list[dict] = []
    for source in sorted(SOURCES):
        cfg = SOURCES[source]
        actual = sorted(by_source.get(source, []))
        expected = 0
        if actual:
            first = actual[0]
            weekday = cfg.get("weekday")
            day = first
            if weekday is not None:
                delta = (weekday - day.weekday()) % 7
                day += timedelta(days=delta)
            while day <= last_archive:
                expected += 1
                day += timedelta(days=cfg["cadence_days"])
        rate = min(len(actual) / expected * 100, 100.0) if expected else 100.0
        rows.append(
            {
                "source": source,
                "expected": expected,
                "actual": len(actual),
                "rate": round(rate, 1),
                "last_fetched": actual[-1] if actual else None,
            }
        )
    return rows
