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
    # With JS available the full nav is collapsed on phones and only expands
    # when requested; without JS it stays visible and flows onto a second row.
    assert ".site-nav" in mobile
    assert ".js .site-nav" in mobile
    assert "display: none" in mobile
    assert ".no-js .site-nav" in mobile
    assert ".no-js .nav-toggle { display: none; }" in mobile
    assert ".nav-toggle" in mobile


def test_html_starts_with_no_js_class_swapped_by_app_script():
    base = (APP_DIR / "templates" / "base.html").read_text()
    assert '<html lang="en" class="no-js">' in base
    assert 'classList.remove("no-js")' in base
    assert 'classList.add("js")' in base


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


def test_shared_layout_has_skip_link_and_active_navigation():
    base = (APP_DIR / "templates" / "base.html").read_text()
    assert 'class="skip-link"' in base
    assert 'id="main-content"' in base
    assert 'aria-current="page"' in base


def test_theme_and_install_controls_have_accessible_state_management():
    base = (APP_DIR / "templates" / "base.html").read_text()
    app_js = (APP_DIR / "static" / "app.js").read_text()
    assert 'aria-describedby="install-dialog-description"' in base
    assert 'Switch to " + labels[next] + " theme' in base
    assert 'event.key === "Escape"' in app_js
    assert 'event.key !== "Tab"' in app_js
    assert "lastFocusedElement.focus()" in app_js


def test_card_scores_are_present_for_curated_sources():
    design = (APP_DIR / "templates" / "design.html").read_text()
    assert "story-score" in CSS
    assert "story-score" not in design


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
    assert "story-links" in story
    assert "story-score" in story
    assert 'id="load-more"' in index


def test_story_cards_can_shrink_without_mobile_overflow():
    assert "min-width: 0" in CSS


def test_story_actions_pin_to_bottom_for_uniform_alignment():
    # Regression: "Read"/"Discuss" drifted at the bottom of each card because
    # the action row sat directly under content. It must pin to the card's
    # bottom edge so the actions align uniformly across grid tiles.
    assert ".story-foot" in CSS
    assert "margin-top: auto" in CSS


def test_stats_has_accessible_trends_table():
    stats = (APP_DIR / "templates" / "stats.html").read_text()
    assert "stat-table--trends" in stats
    assert 'scope="col"' in stats
    assert 'scope="row"' in stats


def test_story_save_button_handles_missing_story_top():
    # Regression: an unguarded `.story-top` lookup would throw and disable
    # every other feature if a future card template drops the element.
    app_js = (APP_DIR / "static" / "app.js").read_text()
    assert 'var top = card.querySelector(".story-top");' in app_js
    assert "if (top) top.appendChild(btn);" in app_js


def test_search_reports_unavailability_not_blank():
    # Regression: a failed /api/search.json fetch used to render "No matches."
    # as if the archive were empty; it must distinguish "unavailable".
    app_js = (APP_DIR / "static" / "app.js").read_text()
    assert "var searchUnavailable = false;" in app_js
    assert "searchUnavailable = true;" in app_js
    assert "Search unavailable" in app_js
    assert ': "No matches."' in app_js
    assert 'searchUnavailable\n        ? "Search unavailable' in app_js


def test_filter_changes_announce_to_screen_readers():
    # Regression: switching source/saved filters changed the visible story set
    # silently; a visually-hidden aria-live region must announce the count,
    # but only after the user has actually touched a filter (not on load).
    app_js = (APP_DIR / "static" / "app.js").read_text()
    index = (APP_DIR / "templates" / "index.html").read_text()
    assert 'id="filter-status" aria-live="polite"' in index
    assert "var filterStatus = document.getElementById" in app_js
    assert "var filtersTouched = false;" in app_js
    assert "filtersTouched = true;" in app_js
    assert "announceFilterCount(matched, visible);" in app_js
    assert "Showing " in app_js


def test_why_read_note_styled_and_present_on_cards():
    story = (APP_DIR / "templates" / "_story.html").read_text()
    css = (APP_DIR / "static" / "style.css").read_text()
    assert '{% if story.why_read %}<p class="story-why-read">' in story
    assert ".story-why-read" in css
    assert "var(--accent-soft)" in css


def test_json_ld_macros_and_block_wired():
    base = (APP_DIR / "templates" / "base.html").read_text()
    index = (APP_DIR / "templates" / "index.html").read_text()
    snapshot = (APP_DIR / "templates" / "snapshot.html").read_text()
    assert "{% block json_ld %}{% endblock %}" in base
    assert '"@type": "WebSite"' in index
    assert '"@type": "SearchAction"' in index
    json_ld = (APP_DIR / "templates" / "_json_ld.html").read_text()
    assert '"@type": "ListItem"' in json_ld
    assert "application/ld+json" in json_ld
    assert (
        '{% from "_json_ld.html" import breadcrumbs, item_list with context %}'
        in snapshot
    )
