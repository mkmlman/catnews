from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "catnews"
TAGLINE = "Curated daily."
BASE_URL = os.environ.get("CATNEWS_BASE_URL", "http://localhost:8000")
# URL prefix the site is served under, e.g. "/catnews" for a GitHub Pages
# project site. Empty string means the site is served from the domain root.
BASE_PATH = os.environ.get("CATNEWS_BASE_PATH", "").rstrip("/")

DATA_DIR = Path(os.environ.get("CATNEWS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

USER_AGENT = "catnews/0.1 (curated digest bot)"
REQUEST_TIMEOUT = 15.0

DIGEST_LIMITS = {
    "hn": int(os.environ.get("CATNEWS_LIMIT_HN", "25")),
    "arxiv": int(os.environ.get("CATNEWS_LIMIT_ARXIV", "15")),
    "github": int(os.environ.get("CATNEWS_LIMIT_GITHUB", "15")),
}
