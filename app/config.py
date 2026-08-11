from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

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

SOURCES_FILE = Path(__file__).resolve().parent.parent / "sources.yaml"

# Badge palette, assigned to sources in definition order unless a source sets
# an explicit `color`. Each entry: (light fg, light bg, dark fg, dark bg).
PALETTE_NAMES: tuple[str, ...] = (
    "ember",
    "clay",
    "graphite",
    "cerulean",
    "moss",
    "amber",
    "plum",
    "teal",
    "rose",
    "steel",
    "olive",
    "bronze",
)

PALETTE: list[tuple[str, str, str, str]] = [
    ("#9c4d14", "#f8e7d2", "#f0b177", "rgba(240, 177, 119, 0.15)"),  # ember
    ("#8a1f18", "#f7e2df", "#f2a7a2", "rgba(242, 167, 162, 0.15)"),  # clay
    ("#3b3e37", "#e9e9e2", "#c8cbc1", "rgba(200, 203, 193, 0.15)"),  # graphite
    ("#20507a", "#dfeaf4", "#9db9db", "rgba(157, 185, 219, 0.15)"),  # cerulean
    ("#2e6b3e", "#e2f0e4", "#a8d4ae", "rgba(168, 212, 174, 0.15)"),  # moss
    ("#7a4a21", "#f3e7d8", "#dcb185", "rgba(220, 177, 133, 0.15)"),  # amber
    ("#5b3e8a", "#ece5f4", "#bdabdd", "rgba(189, 171, 221, 0.15)"),  # plum
    ("#1f6f6b", "#dff0ee", "#9fd3cf", "rgba(159, 211, 207, 0.15)"),  # teal
    ("#8a2e4e", "#f4e4ea", "#dca7bd", "rgba(220, 167, 189, 0.15)"),  # rose
    ("#3f4f73", "#e4e9f3", "#aab7d4", "rgba(170, 183, 212, 0.15)"),  # steel
    ("#6b5b1e", "#f0eedc", "#cfc383", "rgba(207, 195, 131, 0.15)"),  # olive
    ("#6b3f1e", "#f2e8dc", "#cfa37d", "rgba(207, 163, 125, 0.15)"),  # bronze
]

# Fallback used if sources.yaml is missing or empty, so a fresh checkout still
# runs with a sensible default set of sources.
_BUILTIN_SOURCES: dict[str, dict] = {
    "hn": {
        "label": "Hacker News",
        "tag": "HN",
        "type": "builtin",
        "cadence_days": 1,
        "limit": 25,
    },
    "arxiv": {
        "label": "arXiv",
        "tag": "arXiv",
        "type": "builtin",
        "cadence_days": 7,
        "limit": 15,
        "weekday": 0,
    },
    "github": {
        "label": "GitHub",
        "tag": "GitHub",
        "type": "builtin",
        "cadence_days": 1,
        "limit": 15,
    },
    "registerspill": {
        "label": "Register Spill",
        "tag": "Register Spill",
        "type": "rss",
        "url": "https://registerspill.thorstenball.com/feed",
        "url_filter": "joy-and-curiosity",
        "extract_links": True,
        "cadence_days": 7,
        "limit": 10,
        "weekday": 0,
    },
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def load_sources(path: Path | None = None) -> dict[str, dict]:
    """Read source definitions from sources.yaml.

    Each source may set: key, label, tag, type (api|rss), url (for rss),
    cadence_days, limit, weekday, color. Unknown keys are preserved so hosts
    can add their own metadata, but only the above are interpreted.
    """
    path = path or SOURCES_FILE
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
        entries = data.get("sources") or []
        if entries:
            defaults = data.get("defaults") or {}
            sources: dict[str, dict] = {}
            for entry in entries:
                key = str(entry.get("key", "")).strip()
                if not key:
                    continue
                cfg = {**defaults, **entry, "key": key}
                cfg["cadence_days"] = int(cfg.get("cadence_days", 1))
                cfg["limit"] = int(cfg.get("limit", 20))
                sources[key] = cfg
            return sources
    return {k: dict(v) for k, v in _BUILTIN_SOURCES.items()}


SOURCES: dict[str, dict] = load_sources()

SOURCE_LABELS: dict[str, str] = {k: v["label"] for k, v in SOURCES.items()}
SOURCE_TAGS: dict[str, str] = {k: v["tag"] for k, v in SOURCES.items()}


def _apply_env_overrides(sources: dict[str, dict]) -> dict[str, dict]:
    """Preserve the historical per-source cadence/limit env overrides."""
    for key, cfg in sources.items():
        prefix = key.upper()
        cfg["cadence_days"] = _env_int(f"CATNEWS_CADENCE_{prefix}", cfg["cadence_days"])
        cfg["limit"] = _env_int(f"CATNEWS_LIMIT_{prefix}", cfg["limit"])
    return sources


SOURCES = _apply_env_overrides(SOURCES)

WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def cadence_label(key: str) -> str:
    """Human-readable cadence for a source, e.g. 'daily' or 'weekly · Mondays'."""
    cfg = SOURCES[key]
    days = cfg["cadence_days"]
    if days == 1:
        return "daily"
    if (weekday := cfg.get("weekday")) is not None:
        return f"weekly · {WEEKDAYS[weekday]}"
    if days == 7:
        return "weekly"
    return f"every {days} days"


def palette_entries() -> list[dict[str, str]]:
    """Named palette entries for the design-system page (light + dark pairs)."""
    return [
        {
            "name": name,
            "light_fg": fg,
            "light_bg": bg,
            "dark_fg": dark_fg,
            "dark_bg": dark_bg,
        }
        for name, (fg, bg, dark_fg, dark_bg) in zip(PALETTE_NAMES, PALETTE)
    ]


def badge_color(key: str) -> tuple[str, str, str, str]:
    """The badge palette entry for a source (light/dark foreground + background)."""
    cfg = SOURCES[key]
    if override := cfg.get("color"):
        return (override, override, override, override)
    try:
        return PALETTE[list(SOURCES).index(key) % len(PALETTE)]
    except ValueError:
        return PALETTE[-1]


def badge_css() -> str:
    """CSS custom-property + class rules for every source badge (light & dark)."""
    light: list[str] = [":root {"]
    dark: list[str] = ['[data-theme="dark"] {']
    rules: list[str] = []
    for key in SOURCES:
        fg, bg, dark_fg, dark_bg = badge_color(key)
        light.append(f"  --badge-{key}: {fg};")
        light.append(f"  --badge-{key}-bg: {bg};")
        dark.append(f"  --badge-{key}: {dark_fg};")
        dark.append(f"  --badge-{key}-bg: {dark_bg};")
        rules.append(
            f".badge-{key} {{ color: var(--badge-{key}); "
            f"background: var(--badge-{key}-bg); }}"
        )
    light.append("}")
    dark.append("}")
    return "\n".join(light + dark + rules)
