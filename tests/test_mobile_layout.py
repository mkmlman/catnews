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
    # The full nav is collapsed on phones and only expands when requested.
    assert ".site-nav" in mobile
    assert "display: none" in mobile
    assert ".nav-toggle" in mobile


def test_icons_in_fixed_non_wrapping_slot(mobile):
    # Regression: the GitHub icon and theme toggle used to live inside the nav and
    # shifted rows/positions with screen width. They must stay in a dedicated
    # always-nowrap actions slot pinned next to the wordmark.
    assert ".header-actions" in mobile
    assert "grid-area: actions" in mobile
    assert ".site-nav" in mobile
    assert "grid-area: nav" in mobile
    css = (APP_DIR / "static" / "style.css").read_text()
    assert ".header-actions {" in css
    assert "flex-wrap: nowrap" in css


def test_source_filter_chips_never_wrap(mobile):
    # Regression: the homepage Source chips wrapped onto a second row at
    # different points on different phone widths. They must stay a single,
    # scrollable row in a fixed order.
    assert ".filter-row" in mobile
    assert "flex-wrap: nowrap" in mobile
    assert "overflow-x: auto" in mobile
    assert ".filter-scroll-cue" in mobile


def test_source_details_stack_cleanly(mobile):
    # Regression: the Sources page Cadence/Limit/Last-fetched rows scattered to
    # inconsistent x-positions depending on width. They must stack as tidy
    # full-width label/value rows.
    assert ".source-details" in mobile
    assert "flex-direction: column" in mobile


def test_sticky_filter_bar_is_frosted_not_solid():
    # Regression: the sticky Source filter bar used a solid var(--paper) gradient
    # that rendered as a flat dark rectangle over the glowed page top in dark
    # mode. It must be a transparent, blurred (glass) surface — no solid tint.
    css = (APP_DIR / "static" / "style.css").read_text()
    assert "linear-gradient(var(--paper) 82%, rgba(245, 244, 237, 0));" not in css
    assert "backdrop-filter: blur(12px);" in css


def test_no_svg_noise_overlay():
    # Regression: the fixed full-viewport SVG-turbulence grain (body::before)
    # showed through the filter bar as a dark grainy box in dark mode, and can
    # render as a solid black box on iOS Safari. It must be gone.
    css = (APP_DIR / "static" / "style.css").read_text()
    assert "body::before" not in css
    assert "feTurbulence" not in css
    assert "--noise-opacity" not in css


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


def test_static_assets_use_cache_busting_versions():
    base = (APP_DIR / "templates" / "base.html").read_text()
    assert "style.css?v={{ asset_version }}" in base
    assert "app.js?v={{ asset_version }}" in base


def test_mobile_navigation_has_accessible_toggle():
    base = (APP_DIR / "templates" / "base.html").read_text()
    assert 'id="nav-toggle"' in base
    assert 'aria-controls="primary-nav"' in base
    assert 'aria-expanded="false"' in base


def test_story_filters_are_accessible_buttons():
    index = (APP_DIR / "templates" / "index.html").read_text()
    assert 'type="button"' in index
    assert 'aria-pressed="true"' in index
    assert 'aria-controls="stories"' in index


def test_story_previews_are_not_rendered_and_progress_markup_exists():
    story = (APP_DIR / "templates" / "_story.html").read_text()
    index = (APP_DIR / "templates" / "index.html").read_text()
    assert "story-excerpt" not in story
    assert "story-more" not in story
    assert "story-links" not in story
    assert "story-score" not in story
    assert 'id="filter-status"' in index


def test_story_cards_can_shrink_without_mobile_overflow():
    assert "min-width: 0" in CSS


def test_story_actions_follow_metadata_without_stretching_cards():
    assert ".story-foot" in CSS
    assert "margin-top: 0" in CSS


def test_stats_has_accessible_trends_table():
    stats = (APP_DIR / "templates" / "stats.html").read_text()
    assert "stat-table--trends" in stats
    assert 'scope="col"' in stats
    assert 'scope="row"' in stats
