from __future__ import annotations

from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
CSS = (APP_DIR / "static" / "style.css").read_text()


def media_block(name: str) -> str:
    """Return the text of the first `@media <name> { ... }` block."""
    needle = f"@media {name} {{"
    start = CSS.index(needle) + len(needle)
    depth = 1
    i = start
    while i < len(CSS) and depth:
        if CSS[i] == "{":
            depth += 1
        elif CSS[i] == "}":
            depth -= 1
        i += 1
    return CSS[start : i - 1]


@pytest.fixture(scope="module")
def mobile() -> str:
    return media_block("(max-width: 560px)")


def test_mobile_media_query_exists():
    assert "(max-width: 560px)" in CSS


def test_header_nav_wraps_on_mobile(mobile):
    # Regression: the top nav stayed a single non-wrapping row, overflowing the
    # viewport horizontally on phones <=390px. It must wrap instead.
    assert ".site-nav" in mobile
    assert "wrap" in mobile


def test_stat_table_never_overflows_page(mobile):
    # Regression: the 4-column stats table was wider than 320px phones, forcing
    # horizontal page scroll. It must scroll within its section instead.
    assert ".stat-section" in mobile
    assert "overflow-x: auto" in mobile


def test_stories_single_column_on_mobile(mobile):
    assert ".stories" in mobile
    assert "1fr" in mobile


def test_homepage_has_viewport_meta():
    base = (APP_DIR / "templates" / "base.html").read_text()
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in base
