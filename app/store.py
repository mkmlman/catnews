from __future__ import annotations

from datetime import date
from pathlib import Path

from .config import SOURCES, cadence_label, today_utc
from .models import Digest, SiteStats, SourceSnapshot, Story


def snapshot_path(source: str, date_obj: date, data_dir: Path) -> Path:
    return data_dir / f"source_{source}_{date_obj.isoformat()}.json"


def list_snapshot_dates(source: str, data_dir: Path) -> list[date]:
    dates: list[date] = []
    for path in data_dir.glob(f"source_{source}_*.json"):
        try:
            dates.append(date.fromisoformat(path.stem.replace(f"source_{source}_", "")))
        except ValueError:
            continue
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
    path.write_text(snapshot.model_dump_json(indent=2))
    return path


def load_all_snapshots(data_dir: Path) -> list[SourceSnapshot]:
    sources = sorted(
        {path.stem.split("_")[1] for path in data_dir.glob("source_*_*.json")}
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
        {path.stem.split("_")[1] for path in data_dir.glob("source_*_*.json")}
    )


def combined_digest(data_dir: Path, day: date | None = None) -> Digest | None:
    """A Digest combining the latest stories from every source (for RSS/markdown)."""
    stories: list[Story] = []
    for source in SOURCES:
        snap = load_latest_snapshot(source, data_dir)
        if snap:
            stories.extend(snap.stories)
    if not stories:
        return None
    return Digest(date=day or today_utc(), stories=stories)


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
    for snap in snapshots:
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
    )
