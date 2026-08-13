from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

from .config import SOURCES, cadence_label, today_utc
from .models import Digest, SiteStats, SourceSnapshot, Story

FETCH_STATUS_FILE = "fetch-status.json"


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


def load_fetch_report(data_dir: Path) -> dict:
    """Load the last fetch report, if the fetch job has written one."""
    path = data_dir / FETCH_STATUS_FILE
    if not path.is_file():
        return {}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return report if isinstance(report, dict) else {}


def save_fetch_report(day: date, data_dir: Path, statuses: dict[str, dict]) -> Path:
    """Atomically persist the build-time source fetch report."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / FETCH_STATUS_FILE
    temp_path: Path | None = None
    payload = {"date": day.isoformat(), "sources": statuses}
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=data_dir,
            prefix=f".{path.name}.",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(payload, temp_file, indent=2, ensure_ascii=False)
            temp_file.write("\n")
        temp_path.replace(path)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
    return path


def _status_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def fetch_status(data_dir: Path) -> dict:
    """Return display-ready source freshness information for pages and APIs.

    A missing report is treated as a healthy legacy checkout when a snapshot
    exists. This keeps old archives usable while newer fetch jobs add precise
    stale/unavailable diagnostics.
    """
    report = load_fetch_report(data_dir)
    report_sources = report.get("sources")
    if not isinstance(report_sources, dict):
        report_sources = {}

    sources: dict[str, dict] = {}
    for source, cfg in SOURCES.items():
        snapshot = load_latest_snapshot(source, data_dir)
        entry = report_sources.get(source)
        if not isinstance(entry, dict):
            entry = {}

        state = entry.get("state")
        if state not in {"ok", "stale", "unavailable", "skipped", "unknown"}:
            state = "unknown" if snapshot else "unavailable"
        snapshot_date = _status_date(entry.get("snapshot_date"))
        if snapshot_date is None and snapshot:
            snapshot_date = snapshot.date
        if state == "ok" and snapshot is None:
            state = "unavailable"

        labels = {
            "ok": "Current",
            "stale": "Using older snapshot",
            "unavailable": "Unavailable",
            "skipped": "On schedule",
            "unknown": "No fetch report",
        }
        sources[source] = {
            "key": source,
            "label": cfg["label"],
            "state": state,
            "state_label": labels[state],
            "snapshot_date": snapshot_date,
            "stories": entry.get("stories", len(snapshot.stories) if snapshot else 0),
            "detail": str(entry.get("error", ""))[:240],
            "is_issue": state in {"stale", "unavailable"},
        }

    snapshot_dates = [
        row["snapshot_date"] for row in sources.values() if row["snapshot_date"]
    ]
    latest_snapshot = max(snapshot_dates) if snapshot_dates else None
    report_date = _status_date(report.get("date"))
    return {
        "date": report_date,
        "latest_snapshot": latest_snapshot,
        "has_issues": any(row["is_issue"] for row in sources.values()),
        "sources": sources,
    }


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
    status_by_source = fetch_status(data_dir)["sources"]
    for key, cfg in SOURCES.items():
        snap = load_latest_snapshot(key, data_dir)
        status = status_by_source[key]
        rows.append(
            {
                "key": key,
                "label": cfg["label"],
                "tag": cfg["tag"],
                "cadence": cadence_label(key),
                "limit": cfg.get("limit"),
                "last_fetched": snap.date if snap else None,
                "stories": len(snap.stories) if snap else 0,
                "state": status["state"],
                "state_label": status["state_label"],
                "status_detail": status["detail"],
                "is_issue": status["is_issue"],
            }
        )
    return rows


def site_stats(
    data_dir: Path, snapshots: list[SourceSnapshot] | None = None
) -> SiteStats:
    snapshots = load_all_snapshots(data_dir) if snapshots is None else snapshots
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


def weekly_trends(
    data_dir: Path, snapshots: list[SourceSnapshot] | None = None
) -> list[dict]:
    """Story counts by source per ISO week, for the stats trends table.

    Returns a list of dicts (oldest first):
      {"week": "2026-W32", "start": date, "end": date,
       "counts": {"hn": 25, ...}, "total": 27}
    """
    from collections import defaultdict

    snapshots = load_all_snapshots(data_dir) if snapshots is None else snapshots
    buckets: dict[tuple[int, int], dict] = {}
    for snap in snapshots:
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


def daily_counts(
    data_dir: Path, snapshots: list[SourceSnapshot] | None = None
) -> list[dict]:
    """Total story counts per calendar day, zero-filled across the archive span.

    Returns a list of dicts (oldest first), one per day from the first to the
    last snapshot date: {"date": date, "count": int}. Days with no snapshots
    are included with a count of 0 so the stats heatmap shows gaps.
    """
    from collections import defaultdict
    from datetime import timedelta

    snapshots = load_all_snapshots(data_dir) if snapshots is None else snapshots
    counts: dict[date, int] = defaultdict(int)
    for snap in snapshots:
        counts[snap.date] += len(snap.stories)
    if not counts:
        return []
    first = min(counts)
    last = max(counts)
    rows: list[dict] = []
    day = first
    while day <= last:
        rows.append({"date": day, "count": counts[day]})
        day += timedelta(days=1)
    return rows


def top_domains(
    data_dir: Path,
    limit: int = 10,
    snapshots: list[SourceSnapshot] | None = None,
) -> list[tuple[str, int]]:
    """Most common story URL hostnames across all archived snapshots."""
    from collections import Counter
    from urllib.parse import urlparse

    snapshots = load_all_snapshots(data_dir) if snapshots is None else snapshots
    counter: Counter[str] = Counter()
    for snap in snapshots:
        for story in snap.stories:
            host = urlparse(story.url).netloc
            host = host.removeprefix("www.")
            if host:
                counter[host] += 1
    return counter.most_common(limit)


def arxiv_category_counts(
    data_dir: Path, snapshots: list[SourceSnapshot] | None = None
) -> list[tuple[str, int]]:
    """Most common arXiv primary categories across archived arXiv stories."""
    from collections import Counter

    snapshots = load_all_snapshots(data_dir) if snapshots is None else snapshots
    counter: Counter[str] = Counter()
    for snap in snapshots:
        for story in snap.stories:
            if story.category:
                counter[story.category] += 1
    return counter.most_common()


def days_archiving(
    data_dir: Path, snapshots: list[SourceSnapshot] | None = None
) -> int:
    """Number of calendar days spanned by the archive (1 if a single day)."""
    dates = [
        s.date
        for s in (load_all_snapshots(data_dir) if snapshots is None else snapshots)
    ]
    if not dates:
        return 0
    return (max(dates) - min(dates)).days + 1


def fetch_health(
    data_dir: Path, snapshots: list[SourceSnapshot] | None = None
) -> list[dict]:
    """Per-source fetch success: actual snapshots vs expected by cadence.

    Expected count = number of fetch dates the source's cadence implies,
    anchored at the source's own first snapshot and spanning through the
    most recent archive date.
    """
    from datetime import timedelta

    from .config import SOURCES

    snapshots = load_all_snapshots(data_dir) if snapshots is None else snapshots
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
