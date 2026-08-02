from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Digest, SiteStats, Story


def digest_path(date_obj: date, data_dir: Path) -> Path:
    return data_dir / f"digest_{date_obj.isoformat()}.json"


def list_editions(data_dir: Path) -> list[date]:
    editions: list[date] = []
    for path in data_dir.glob("digest_*.json"):
        try:
            editions.append(date.fromisoformat(path.stem.replace("digest_", "")))
        except ValueError:
            continue
    return sorted(editions)


def load_digest(date_obj: date, data_dir: Path) -> Digest | None:
    path = digest_path(date_obj, data_dir)
    if not path.exists():
        return None
    return Digest.model_validate_json(path.read_text())


def load_latest(data_dir: Path) -> Digest | None:
    editions = list_editions(data_dir)
    if not editions:
        return None
    return load_digest(editions[-1], data_dir)


def save_digest(digest: Digest, data_dir: Path) -> Path:
    path = digest_path(digest.date, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(digest.model_dump_json(indent=2))
    return path


def load_all(data_dir: Path) -> list[Digest]:
    return [d for d in (load_digest(e, data_dir) for e in list_editions(data_dir)) if d]


def site_stats(data_dir: Path) -> SiteStats:
    digests = load_all(data_dir)
    total = 0
    by_source: dict[str, int] = {}
    by_signal: dict[str, int] = {}
    for d in digests:
        total += len(d.stories)
        for s in d.stories:
            by_source[s.source] = by_source.get(s.source, 0) + 1
            by_signal[s.signal] = by_signal.get(s.signal, 0) + 1
    return SiteStats(
        total_stories=total,
        editions=len(digests),
        first_edition=digests[0].date if digests else None,
        last_edition=digests[-1].date if digests else None,
        by_source=dict(sorted(by_source.items())),
        by_signal=dict(sorted(by_signal.items())),
    )
