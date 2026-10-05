from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def site_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    site_dir = tmp_path_factory.mktemp("browser-site") / "site"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_site.py"),
            "--out",
            str(site_dir),
            "--base-path",
            "",
            "--base-url",
            "http://127.0.0.1",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(port),
            "--bind",
            "127.0.0.1",
            "--directory",
            str(site_dir),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            if server.poll() is not None:
                raise RuntimeError("Static-site preview server exited unexpectedly")
            try:
                urllib.request.urlopen(url, timeout=1).close()
                break
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        else:
            raise RuntimeError("Static-site preview server did not start")
        yield url
    finally:
        server.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            server.wait(timeout=5)
        if server.poll() is None:
            server.kill()
            server.wait()


@pytest.fixture
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def page(browser: Browser, site_url: str) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    current = context.new_page()
    current.goto(site_url, wait_until="networkidle")
    yield current
    context.close()


def test_source_filter_save_and_saved_view(page: Page) -> None:
    page.locator('.chip[data-source="hn"]').click()
    visible = page.locator(".story:visible")
    assert visible.count() == 12  # First page of the 25-story HN source.
    assert page.locator(".story:visible:not([data-source='hn'])").count() == 0

    first = visible.first
    first.locator(".save-toggle").click()
    page.locator('.chip[data-saved="saved"]').click()
    assert page.locator(".story:visible").count() == 1
    assert page.locator(".story:visible .save-toggle[aria-pressed='true']").count() == 1
    assert "saved=1" in page.url


def test_archive_search_and_deep_link_reveal(page: Page) -> None:
    search = page.locator("#search-input")
    search.fill("python")
    page.locator("a.search-result").first.wait_for()
    assert page.locator("a.search-result").count() > 0

    last_story = page.locator(".story").last
    story_id = last_story.get_attribute("id")
    assert story_id
    page.evaluate("id => { location.hash = id; }", story_id)
    assert last_story.is_visible()
    assert last_story.evaluate("el => !el.hidden")


def test_layout_and_theme_controls(page: Page) -> None:
    page.get_by_role("button", name="Editorial list view").click()
    assert page.locator("#stories").evaluate("el => el.classList.contains('view-list')")
    page.get_by_role("button", name="Card grid view").click()
    assert not page.locator("#stories").evaluate(
        "el => el.classList.contains('view-list')"
    )

    page.locator("#theme-toggle").click()
    page.locator('[data-theme-option="dark"]').click()
    assert page.locator("html").get_attribute("data-theme") == "dark"


def test_mobile_widths_navigation_and_no_horizontal_overflow(page: Page) -> None:
    for width in (320, 360, 390, 768):
        page.set_viewport_size({"width": width, "height": 844})
        page.wait_for_timeout(100)
        dimensions = page.evaluate(
            "({viewport: innerWidth, document: document.documentElement.scrollWidth})"
        )
        assert dimensions["document"] <= dimensions["viewport"], dimensions

    page.set_viewport_size({"width": 390, "height": 844})
    mobile_result = Axe().run(page)
    mobile_failures = [
        violation["id"]
        for violation in mobile_result.response["violations"]
        if violation["impact"] in {"critical", "serious"}
    ]
    assert not mobile_failures, ", ".join(mobile_failures)

    page.locator("#nav-toggle").click()
    assert page.locator("#nav-toggle").get_attribute("aria-expanded") == "true"
    page.keyboard.press("Escape")
    assert page.locator("#nav-toggle").get_attribute("aria-expanded") == "false"

    page.locator("#help-toggle").click()
    assert page.locator("#help-dialog").is_visible()
    page.keyboard.press("Escape")
    page.locator("#help-dialog").wait_for(state="hidden")


def test_accessibility_critical_and_serious_violations(
    page: Page, site_url: str
) -> None:
    axe = Axe()
    # Avoid sampling interpolated colors mid-transition; contrast is checked
    # against the stable rendered UI, and reduced-motion is an important mode.
    page.emulate_media(reduced_motion="reduce")
    urls = (
        site_url,
        f"{site_url}/archive/",
        f"{site_url}/stats/",
        f"{site_url}/sources/",
    )
    failures: list[str] = []
    for url in urls:
        page.goto(url, wait_until="networkidle")
        result = axe.run(page)
        for violation in result.response["violations"]:
            if violation["impact"] in {"critical", "serious"}:
                failures.append(
                    f"{url}: {violation['id']} ({violation['impact']}) "
                    f"{len(violation['nodes'])} node(s)"
                )
    assert not failures, "\n".join(failures)
