from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

APP_NAME = "catnews"


def today_utc() -> date:
    """Today's date in UTC (avoid naive local datetime.date.today())."""
    return datetime.now(UTC).date()


BASE_URL = os.environ.get("CATNEWS_BASE_URL", "http://localhost:8000")
# URL prefix the site is served under, e.g. "/catnews" for a GitHub Pages
# project site. Empty string means the site is served from the domain root.
BASE_PATH = os.environ.get("CATNEWS_BASE_PATH", "").rstrip("/")

DATA_DIR = Path(
    os.environ.get("CATNEWS_DATA_DIR", Path(__file__).resolve().parent.parent / "data")
)

USER_AGENT = "catnews/0.1 (curated digest bot)"
REQUEST_TIMEOUT = 15.0

# Each source is fetched independently on its own cadence and archived as a
# separate snapshot. cadence_days = minimum days between fetches.
SOURCES: dict[str, dict] = {
    "hn": {
        "label": "Hacker News",
        "cadence_days": int(os.environ.get("CATNEWS_CADENCE_HN", "1")),
        "limit": int(os.environ.get("CATNEWS_LIMIT_HN", "25")),
    },
    "arxiv": {
        "label": "arXiv",
        "cadence_days": int(os.environ.get("CATNEWS_CADENCE_ARXIV", "7")),
        "limit": int(os.environ.get("CATNEWS_LIMIT_ARXIV", "15")),
    },
    "github": {
        "label": "GitHub",
        "cadence_days": int(os.environ.get("CATNEWS_CADENCE_GITHUB", "1")),
        "limit": int(os.environ.get("CATNEWS_LIMIT_GITHUB", "15")),
    },
    "registerspill": {
        "label": "Register Spill",
        "cadence_days": int(os.environ.get("CATNEWS_CADENCE_REGISTERSPILL", "7")),
        "limit": int(os.environ.get("CATNEWS_LIMIT_REGISTERSPILL", "10")),
        # Fetch only on the preferred weekday (0 = Monday). The daily 07:00 UTC
        # schedule then naturally lands the weekly fetch on Monday mornings.
        "weekday": 0,
    },
}

SOURCE_LABELS: dict[str, str] = {k: v["label"] for k, v in SOURCES.items()}
