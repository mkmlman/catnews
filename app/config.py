from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "catnews"
TAGLINE = "Papers and Threads Worth Your Time"
BASE_URL = os.environ.get("CATNEWS_BASE_URL", "http://localhost:8000")

DATA_DIR = Path(os.environ.get("CATNEWS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

USER_AGENT = "catnews/0.1 (curated digest bot)"
REQUEST_TIMEOUT = 15.0

DIGEST_LIMITS = {
    "hn": int(os.environ.get("CATNEWS_LIMIT_HN", "25")),
    "arxiv": int(os.environ.get("CATNEWS_LIMIT_ARXIV", "15")),
    "github": int(os.environ.get("CATNEWS_LIMIT_GITHUB", "15")),
}
