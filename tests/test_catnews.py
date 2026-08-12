from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.fetchers.arxiv import parse_entry
from app.fetchers.github import parse_item
from app.fetchers.hn import parse_hit
from app.fetchers.rss import parse_entry as parse_rss_entry
from app.fetchers.rss import parse_links, strip_html
from app.models import SourceSnapshot, Story
from app.render import live_site_urls, search_index, site_version
from app.store import (
    arxiv_category_counts,
    combined_digest,
    days_archiving,
    fetch_health,
    fetch_status,
    latest_stories_by_source,
    load_all_snapshots,
    save_fetch_report,
    save_snapshot,
    site_stats,
    source_registry,
    top_domains,
    weekly_trends,
)
from scripts.fetch_digest import due_sources

SAMPLE_HIT = {
    "objectID": "49138188",
    "title": "Diátaxis",
    "url": "https://diataxis.fr/",
    "author": "ryanseys",
    "points": 120,
    "num_comments": 42,
    "story_text": "A systematic approach to documentation.",
    "created_at": "2026-07-29T09:00:00.000Z",
}


def test_hn_parse_hit():
    story = parse_hit(SAMPLE_HIT)
    assert story.source == "hn"
    assert story.title == "Diátaxis"
    assert story.url == "https://diataxis.fr/"
    assert story.hn_url == "https://news.ycombinator.com/item?id=49138188"
    assert story.score == 120
    assert story.snippet == "A systematic approach to documentation."


def test_hn_parse_hit_no_url_uses_hn_item():
    hit = {**SAMPLE_HIT, "url": None}
    story = parse_hit(hit)
    assert story.url == "https://news.ycombinator.com/item?id=49138188"


ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2607.28628v1</id>
    <published>2026-07-29T17:00:00Z</published>
    <title>Learning to Trace Seiberg Dualities</title>
    <author><name>Jonathan J. Heckman</name></author>
    <author><name>Shani Meynet</name></author>
    <summary>We study tracing via local models.</summary>
    <arxiv:primary_category term="hep-th"/>
  </entry>
</feed>"""


def test_arxiv_parse_entry():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(ARXIV_XML)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    assert entry is not None
    story = parse_entry(entry)
    assert story is not None
    assert story.source == "arxiv"
    assert story.external_id == "2607.28628v1"
    assert story.authors == ["Jonathan J. Heckman", "Shani Meynet"]
    assert story.url == "http://arxiv.org/abs/2607.28628v1"
    assert story.category == "hep-th"


def test_github_parse_item():
    item = {
        "full_name": "MoonshotAI/Kimi-K3",
        "html_url": "https://github.com/MoonshotAI/Kimi-K3",
        "description": "A 2.78T parameter model.",
        "stargazers_count": 9999,
        "owner": {"login": "MoonshotAI"},
        "created_at": "2026-07-20T00:00:00Z",
    }
    story = parse_item(item)
    assert story.source == "github"
    assert story.title == "MoonshotAI/Kimi-K3"
    assert story.score == 9999


def test_registerspill_parse_links():
    body = (
        '<p>Re-read <a href="https://sahillavingia.com/reflecting">Reflecting on My Failure</a>.</p>'
        '<p>Met <a href="https://x.com/adamwathan">Adam</a> in person.</p>'
        '<a href="https://x.com/jeremygiffon/status/123">Grip Strength</a>'
        '<a href="https://substackcdn.com/image/1">img</a>'
    )
    links = parse_links(body)
    titles = [l.title for l in links]
    assert "Reflecting on My Failure" in titles
    assert "Grip Strength" in titles
    assert "Adam" not in titles
    assert all(l.site for l in links)
    assert all("substackcdn" not in l.url for l in links)


def test_rss_url_filter_keeps_only_matching_entries():
    joy = {
        "link": "https://registerspill.thorstenball.com/p/joy-and-curiosity-93",
        "title": "Joy & Curiosity #93",
    }
    other = {
        "link": "https://registerspill.thorstenball.com/p/ownership",
        "title": "Ownership",
    }
    assert (
        parse_rss_entry(joy, "registerspill", url_filter="joy-and-curiosity")
        is not None
    )
    assert (
        parse_rss_entry(other, "registerspill", url_filter="joy-and-curiosity") is None
    )


def test_rss_parse_entry():
    entry = {
        "title": "On child birth",
        "link": "https://www.henrikkarlsson.xyz/p/child-birth",
        "author": "Henrik Karlsson",
        "summary": "<p>Some <b>html</b> summary.</p>",
        "published_parsed": (2026, 7, 29, 9, 55, 8, 2, 210, 0),
        "id": "https://www.henrikkarlsson.xyz/p/child-birth",
    }
    story = parse_rss_entry(entry, "escflat")
    assert story is not None
    assert story.source == "escflat"
    assert story.title == "On child birth"
    assert story.author == "Henrik Karlsson"
    assert story.external_id == "https://www.henrikkarlsson.xyz/p/child-birth"
    assert story.published is not None
    assert story.snippet is not None
    assert "html" in story.snippet


def test_rss_parse_entry_skips_missing_link():
    assert parse_rss_entry({"title": "No link"}, "escflat") is None


def test_rss_strip_html():
    assert strip_html("<p>Hello &amp; <b>world</b></p>") == "Hello & world"
    assert strip_html("") == ""


def test_fetch_rss_extracts_links_when_requested():
    import asyncio

    from app.fetchers.rss import fetch_rss

    feed_xml = (
        "<rss version='2.0'><channel>"
        "<item><title>Joy &amp; Curiosity #93</title>"
        "<link>https://registerspill.thorstenball.com/p/joy-and-curiosity-93</link>"
        "<author>Thorsten Ball</author>"
        "<content:encoded xmlns:content='http://purl.org/rss/1.0/modules/content/'>"
        '<![CDATA[<p>See <a href="https://gwern.net/">gwern</a>.</p>]]>'
        "</content:encoded></item>"
        "<item><title>Ownership</title>"
        "<link>https://registerspill.thorstenball.com/p/ownership</link>"
        "</item>"
        "</channel></rss>"
    )

    class FakeClient:
        async def get(self, url, timeout=None):
            response = SimpleNamespace(content=feed_xml.encode())
            response.raise_for_status = lambda: None
            return response

    async def run():
        return await fetch_rss(
            FakeClient(),
            "https://registerspill.thorstenball.com/feed",
            "registerspill",
            url_filter="joy-and-curiosity",
            extract_links=True,
        )

    stories = asyncio.run(run())
    assert [s.title for s in stories] == ["Joy & Curiosity #93"]
    assert stories[0].source == "registerspill"
    assert [l.title for l in stories[0].links] == ["gwern"]


def test_story_markdown_and_why_read():
    story = Story(
        source="hn",
        title="T",
        url="https://example.com",
        byline="alice",
        why_read="Short.",
    )
    md = story.to_markdown()
    assert "**Why read:** Short." in md
    assert "## [T](https://example.com)" in md


def test_snapshot_store_roundtrip(tmp_path):
    snap = SourceSnapshot(
        source="hn",
        date=date(2026, 8, 2),
        stories=[
            Story(source="hn", title="A", url="https://a"),
            Story(source="hn", title="B", url="https://b"),
        ],
    )
    path = save_snapshot(snap, tmp_path)
    assert path.exists()

    loaded = SourceSnapshot.model_validate_json(path.read_text())
    assert [s.title for s in loaded.stories] == ["A", "B"]

    stats = site_stats(tmp_path)
    assert stats.total_stories == 2
    assert stats.editions == 1
    assert stats.by_source == {"hn": 2}
    assert stats.snapshots_by_source == {"hn": 1}

    latest = latest_stories_by_source(tmp_path)
    assert [s.title for s in latest["hn"]] == ["A", "B"]


def test_snapshot_store_supports_source_keys_with_underscores(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="my_source",
            date=date(2026, 8, 2),
            stories=[Story(source="my_source", title="A", url="https://a")],
        ),
        tmp_path,
    )

    snapshots = load_all_snapshots(tmp_path)
    assert [(s.source, s.date) for s in snapshots] == [("my_source", date(2026, 8, 2))]
    assert list(latest_stories_by_source(tmp_path)) == ["my_source"]


def test_fetch_one_can_skip_curation(monkeypatch, tmp_path):
    from scripts import fetch_digest

    save_curation = tmp_path / "curation_2026-08-02.json"
    save_curation.write_text('{"stories": {"hn:1": {"why_read": "Curated note"}}}')

    async def fake_fetch(_client):
        return [
            Story(
                source="hn",
                title="A",
                url="https://a",
                external_id="1",
            )
        ]

    monkeypatch.setattr(fetch_digest, "get_fetcher", lambda _cfg: fake_fetch)

    async def run(apply_curation_overrides):
        return await fetch_digest.fetch_one(
            None,
            "hn",
            10,
            date(2026, 8, 2),
            tmp_path,
            apply_curation_overrides=apply_curation_overrides,
        )

    curated = asyncio.run(run(True))
    uncurated = asyncio.run(run(False))
    assert curated.stories[0].why_read == "Curated note"
    assert uncurated.stories[0].why_read is None


def test_fetch_one_retries_transient_http_errors(monkeypatch, tmp_path):
    from scripts import fetch_digest

    calls = 0

    async def flaky_fetch(_client):
        nonlocal calls
        calls += 1
        if calls < 3:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(
                503, request=request, headers={"Retry-After": "0"}
            )
            raise httpx.HTTPStatusError(
                "temporary outage", request=request, response=response
            )
        return [Story(source="hn", title="Recovered", url="https://a")]

    monkeypatch.setattr(fetch_digest, "get_fetcher", lambda _cfg: flaky_fetch)
    monkeypatch.setattr(fetch_digest, "FETCH_ATTEMPTS", 3)
    monkeypatch.setattr(fetch_digest, "FETCH_BACKOFF_SECONDS", 0.0)

    snapshot = asyncio.run(
        fetch_digest.fetch_one(None, "hn", 10, date(2026, 8, 2), tmp_path)
    )
    assert calls == 3
    assert snapshot.stories[0].title == "Recovered"


def test_combined_digest_merges_latest_per_source(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 1),
            stories=[Story(source="hn", title="HN1", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN2", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 2),
            stories=[Story(source="arxiv", title="PAPER", url="https://b")],
        ),
        tmp_path,
    )
    digest = combined_digest(tmp_path)
    assert digest is not None
    assert [s.title for s in digest.stories] == ["HN2", "PAPER"]


def test_combined_digest_interleaves_sources(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(source="hn", title="HN1", url="https://a"),
                Story(source="hn", title="HN2", url="https://a"),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 2),
            stories=[Story(source="arxiv", title="PAPER", url="https://b")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="github",
            date=date(2026, 8, 2),
            stories=[Story(source="github", title="REPO", url="https://c")],
        ),
        tmp_path,
    )
    digest = combined_digest(tmp_path)
    assert digest is not None
    assert [s.source for s in digest.stories] == ["hn", "arxiv", "github", "hn"]


def test_search_index_deduplicates_historical_stories():
    snapshots = [
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 1),
            stories=[Story(source="hn", external_id="1", title="Old", url="https://a")],
        ),
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(
                    source="hn",
                    external_id="1",
                    title="New",
                    url="https://a",
                    snippet="Updated",
                )
            ],
        ),
    ]
    index = search_index(snapshots)
    assert len(index) == 1
    assert index[0]["title"] == "New"
    assert index[0]["snippet"] == "Updated"


def test_static_site_version_changes_when_artifact_changes(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("first")
    first = site_version(site)
    (site / "index.html").write_text("second")
    assert site_version(site) != first


def test_registerspill_only_due_on_mondays(tmp_path):
    # 2026-08-03 is a Monday. Snapshot it so it's not a bootstrap fetch.
    save_snapshot(
        SourceSnapshot(source="registerspill", date=date(2026, 8, 3), stories=[]),
        tmp_path,
    )

    tuesday = date(2026, 8, 4)
    monday_next_week = date(2026, 8, 10)

    # Not enough elapsed time on Tuesday even though a fetch ran Monday.
    assert "registerspill" not in due_sources(tuesday, tmp_path)
    # A week later, on Monday, it becomes due again.
    assert "registerspill" in due_sources(monday_next_week, tmp_path)
    # But not on the intervening Tuesday.
    assert "registerspill" not in due_sources(date(2026, 8, 11), tmp_path)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import main as app_main

    monkeypatch.setattr(app_main, "DATA_DIR", tmp_path)
    with TestClient(app_main.app) as c:
        yield c


def test_api_empty_returns_404(client):
    assert client.get("/api/digest").status_code == 404
    assert client.get("/").status_code == 200


def test_api_pages_and_filters(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 2),
            stories=[Story(source="arxiv", title="arXiv paper", url="https://b")],
        ),
        tmp_path,
    )

    assert client.get("/").status_code == 200
    assert client.get("/archive/").status_code == 200
    archive = client.get("/archive/").text
    assert "Hacker News" in archive
    assert "Sunday" in archive
    assert "1 story" in archive
    assert client.get("/stats/").status_code == 200
    assert client.get("/sources/").status_code == 200
    assert client.get("/api/").status_code == 200
    assert client.get("/design/").status_code == 200
    assert client.get("/feed.rss").status_code == 200

    body = client.get("/api/stories", params={"source": "hn"}).json()
    assert [s["title"] for s in body] == ["HN story"]

    md = client.get("/api/stories.md").text
    assert "### 1. HN story" in md

    snap = client.get("/api/sources/hn").json()
    assert snap["source"] == "hn"
    assert client.get("/api/sources/hn.json").json() == snap
    assert client.get("/api/sources/nope").status_code == 404
    assert client.get("/api/sources/hn/2026-08-02").status_code == 200

    page = client.get("/archive/hn/2026-08-02/")
    assert page.status_code == 200
    assert "HN story" in page.text
    assert client.get("/archive/nope/2026-08-02/").status_code == 404


def test_sources_page_lists_sources(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="registerspill",
            date=date(2026, 8, 3),  # a Monday
            stories=[Story(source="registerspill", title="SP", url="https://x")],
        ),
        tmp_path,
    )
    page = client.get("/sources/")
    assert page.status_code == 200
    assert "Hacker News" in page.text
    assert "daily" in page.text
    assert "Register Spill" in page.text
    assert "weekly · Monday" in page.text


def test_source_registry_cadences(tmp_path):
    rows = {r["key"]: r for r in source_registry(tmp_path)}
    assert rows["hn"]["cadence"] == "daily"
    assert rows["arxiv"]["cadence"] == "weekly · Monday"
    assert rows["registerspill"]["cadence"] == "weekly · Monday"
    assert rows["hn"]["last_fetched"] is None


def test_fetch_status_reports_stale_sources(tmp_path):
    from app.config import SOURCES

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 10),
            stories=[Story(source="hn", title="Older", url="https://a")],
        ),
        tmp_path,
    )
    statuses = {
        source: {"state": "skipped", "snapshot_date": None, "stories": 0}
        for source in SOURCES
    }
    statuses["hn"] = {
        "state": "stale",
        "snapshot_date": "2026-08-10",
        "stories": 1,
        "error": "temporary outage",
    }
    save_fetch_report(date(2026, 8, 11), tmp_path, statuses)

    report = fetch_status(tmp_path)
    assert report["date"] == date(2026, 8, 11)
    assert report["has_issues"] is True
    assert report["sources"]["hn"]["state_label"] == "Using older snapshot"
    assert report["sources"]["hn"]["snapshot_date"] == date(2026, 8, 10)
    assert report["sources"]["hn"]["detail"] == "temporary outage"


def test_build_site_copies_all_static_assets(tmp_path):
    # Regression: build_site only copied style.css + fonts, so favicon.svg 404'd
    # on the deployed site. The whole static dir must be copied.
    from pathlib import Path

    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    out = tmp_path / "site"
    out.mkdir()
    (out / "stale-page.html").write_text("old build")
    build_site(tmp_path, out, "/catnews", "https://example.com")

    app_static = Path(__file__).resolve().parent.parent / "app" / "static"
    for name in ("favicon.svg", "style.css"):
        assert (out / "static" / name).read_bytes() == (app_static / name).read_bytes()
    assert (out / "static" / "fonts").is_dir()
    assert (out / "static" / "favicon.svg").exists()
    assert not (out / "stale-page.html").exists()
    assert (out / "api" / "search.json").exists()
    assert (out / "api" / "fetch-status.json").exists()
    assert (out / "api" / "sources" / "hn.json").exists()

    from scripts.check_site import check_site

    assert check_site(out, "/catnews") == []


def test_config_loads_default_sources(tmp_path):
    from app.config import SOURCE_LABELS, SOURCE_TAGS, SOURCES

    assert "hn" in SOURCES
    assert "arxiv" in SOURCES
    assert SOURCE_LABELS["github"] == "GitHub"
    assert SOURCE_TAGS["registerspill"] == "Register Spill"
    assert SOURCES["arxiv"]["weekday"] == 0


def test_config_loads_yaml_sources(tmp_path):
    from app.config import load_sources

    yaml_file = tmp_path / "sources.yaml"
    yaml_file.write_text(
        """
defaults:
  cadence_days: 1
  limit: 5
sources:
  - key: blog
    label: My Blog
    tag: BLOG
    type: rss
    url: https://example.com/feed
    color: "#123456"
  - key: hn
    label: Hacker News
    tag: HN
    type: builtin
    limit: 30
"""
    )
    sources = load_sources(yaml_file)
    assert set(sources) == {"blog", "hn"}
    assert sources["blog"]["type"] == "rss"
    assert sources["blog"]["url"] == "https://example.com/feed"
    # defaults applied, per-source limit overrides
    assert sources["blog"]["cadence_days"] == 1
    assert sources["blog"]["limit"] == 5
    assert sources["hn"]["limit"] == 30


def test_config_falls_back_to_builtin_when_yaml_missing(tmp_path):
    from app.config import load_sources

    missing = tmp_path / "nope.yaml"
    assert not missing.exists()
    sources = load_sources(missing)
    assert set(sources) == {"hn", "arxiv", "github", "registerspill"}


def test_badge_css_covers_every_source():
    from app.config import SOURCES, badge_css

    css = badge_css()
    for key in SOURCES:
        assert f".badge-{key} {{" in css
        assert f"--badge-{key}:" in css
    assert '[data-theme="dark"]' in css


def test_get_fetcher_rss_and_api():
    from app.fetchers import get_fetcher

    rss_fn = get_fetcher({"key": "blog", "type": "rss", "url": "https://x/feed"})
    assert callable(rss_fn)
    hn_fn = get_fetcher({"key": "hn", "type": "builtin"})
    assert callable(hn_fn)

    with pytest.raises(KeyError):
        get_fetcher({"key": "bogus", "type": "builtin"})


def test_build_site_emits_pwa_files(tmp_path):
    # PWA: the static build must ship a manifest + service worker whose
    # precache covers the whole site for full offline browsing.
    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    out = tmp_path / "site"
    build_site(tmp_path, out, "/catnews", "https://example.com")

    manifest = (out / "manifest.json").read_text()
    import json

    data = json.loads(manifest)
    assert data["name"].startswith("catnews")
    assert data["start_url"] == "./"
    assert data["display"] == "standalone"

    sw = (out / "sw.js").read_text()
    assert "PRECACHE" in sw
    # every emitted file (index, archive, static assets, api) is precached
    for rel in ('"./"', '"./index.html"', '"./archive/hn/2026-08-02/"'):
        assert rel in sw, f"missing {rel} in precache"
    assert '"./static/style.css"' in sw
    assert '"./api/stories.json"' in sw
    assert '"./api/search.json"' in sw
    assert '"./api/fetch-status.json"' in sw


def test_deploy_workflow_shares_pages_env_with_validation():
    from pathlib import Path

    import yaml

    workflow = yaml.safe_load(
        (
            Path(__file__).resolve().parent.parent
            / ".github"
            / "workflows"
            / "deploy.yml"
        ).read_text()
    )
    deploy = workflow["jobs"]["deploy"]
    assert deploy["env"]["BASE_PATH"] == "/${{ github.event.repository.name }}"
    assert deploy["env"]["BASE_URL"] == (
        "https://${{ github.event.repository.owner.login }}.github.io/"
        "${{ github.event.repository.name }}"
    )
    build = next(
        step for step in deploy["steps"] if step.get("name") == "Build static site"
    )
    validate = next(
        step for step in deploy["steps"] if step.get("name") == "Validate static site"
    )
    assert "env" not in build
    assert "env" not in validate
    assert '"$BASE_PATH"' in build["run"]
    assert '"$BASE_PATH"' in validate["run"]
    assert workflow["permissions"] == {}
    assert workflow["jobs"]["archive"]["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert workflow["jobs"]["lint"]["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["deploy"]["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }


def test_index_page_has_app_js_and_search(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    page = client.get("/").text
    # shared client script + PWA wiring present on every page
    assert 'src="/static/app.js?v=' in page
    assert 'rel="manifest"' in page
    assert 'register("/sw.js")' in page
    # search box is in the header
    assert 'id="search-input"' in page
    # story cards carry the URL needed by save/read/search
    assert 'data-url="https://a"' in page
    # filter affordances for the new reading model
    assert 'data-saved="saved"' in page
    assert 'id="hide-read"' in page
    # keyword filter + load-more for the growing feed
    assert 'id="keyword-filter"' in page
    assert 'id="load-more"' in page


def test_per_story_timestamp_rendered(client, tmp_path):
    # Each story card shows its published date so a daily digest is scannable.
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(
                    source="hn",
                    title="Timed story",
                    url="https://a",
                    published=datetime(2026, 8, 1, 9, 30, tzinfo=UTC),
                ),
                Story(source="hn", title="No date", url="https://b"),
            ],
        ),
        tmp_path,
    )
    page = client.get("/").text
    assert '<time datetime="2026-08-01T09:30:00+00:00">Aug 01, 2026</time>' in page
    assert "Aug 01, 2026" in page


def test_story_previews_are_not_rendered_on_cards(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 10),
            stories=[
                Story(
                    source="arxiv",
                    title="CoinRAG: Contextualized Information Nugget KV Cache Reuse",
                    url="https://arxiv.org/abs/2608.07458",
                    snippet="Recent optimization studies on Retrieval-Augmented Generation (RAG) have exploited chunk-level KV cache reuse.",
                )
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 10),
            stories=[
                Story(
                    source="hn",
                    title="Upvoted story",
                    url="https://news.example/1",
                    score=482,
                ),
                Story(
                    source="github",
                    title="Stared repo",
                    url="https://github.com/a/b",
                    score=999,
                ),
            ],
        ),
        tmp_path,
    )
    page = client.get("/").text
    assert "CoinRAG: Contextualized Information Nugget KV Cache Reuse" in page
    assert "Recent optimization studies on Retrieval-Augmented Generation" not in page
    assert "story-excerpt" not in page
    assert "story-more" not in page
    assert "story-links" not in page
    # scores ARE rendered for sources that carry them (HN points, GitHub stars)
    assert '<span class="story-score">▲ 482</span>' in page
    assert '<span class="story-score">★ 999</span>' in page


def test_live_app_serves_pwa(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"] == "application/manifest+json"
    assert manifest.json()["short_name"] == "catnews"
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/api/search.json").status_code == 200
    assert client.get("/api/fetch-status.json").status_code == 200

    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert sw.headers["content-type"] == "application/javascript"
    assert "PRECACHE" in sw.text
    assert '"./static/"' not in sw.text
    assert '"./archive/hn/2026-08-02/"' in sw.text

    assert "./static/" not in live_site_urls(
        [SourceSnapshot(source="hn", date=date(2026, 8, 2), stories=[])]
    )
    assert "./api/search.json" in live_site_urls(
        [SourceSnapshot(source="hn", date=date(2026, 8, 2), stories=[])]
    )
    assert "./api/fetch-status.json" in live_site_urls(
        [SourceSnapshot(source="hn", date=date(2026, 8, 2), stories=[])]
    )


def test_api_json_aliases_match_static_build(client, tmp_path):
    # The client-side search fetches /api/search.json; the live app must
    # expose the same .json endpoints the static build emits.
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="Searchable story", url="https://a")],
        ),
        tmp_path,
    )
    for path in (
        "/api/stories.json",
        "/api/search.json",
        "/api/fetch-status.json",
        "/api/digest.json",
        "/api/stats.json",
        "/api/sources.json",
        "/api/sources/hn.json",
    ):
        assert client.get(path).status_code == 200, path
    stories = client.get("/api/stories.json").json()
    assert [s["title"] for s in stories] == ["Searchable story"]
    search = client.get("/api/search.json").json()
    assert [s["title"] for s in search] == ["Searchable story"]


def test_seo_meta_tags_on_pages(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    page = client.get("/").text
    # Open Graph
    assert 'property="og:site_name" content="catnews"' in page
    assert 'property="og:type" content="website"' in page
    assert 'property="og:title"' in page
    assert 'property="og:url"' in page
    assert 'property="og:image"' in page
    # Twitter card
    assert 'name="twitter:card" content="summary"' in page
    assert 'name="twitter:title"' in page
    assert 'name="twitter:image"' in page
    # RSS autodiscovery link
    assert 'rel="alternate" type="application/rss+xml"' in page
    assert 'href="http://localhost:8000/feed.rss"' in page


def test_weekly_trends_buckets_by_iso_week(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[
                Story(source="hn", title="HN1", url="https://a"),
                Story(source="hn", title="HN2", url="https://b"),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="github",
            date=date(2026, 8, 4),
            stories=[Story(source="github", title="Repo", url="https://c")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 10),
            stories=[Story(source="arxiv", title="Paper", url="https://d")],
        ),
        tmp_path,
    )

    trends = weekly_trends(tmp_path)
    assert [r["week"] for r in trends] == ["2026-W32", "2026-W33"]
    assert trends[0]["counts"] == {"github": 1, "hn": 2}
    assert trends[0]["total"] == 3
    assert trends[1]["counts"] == {"arxiv": 1}
    assert trends[1]["start"] == date(2026, 8, 10)


def test_top_domains_and_arxiv_categories(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[
                Story(source="hn", title="A", url="https://www.bbc.com/news/a"),
                Story(source="hn", title="B", url="https://bbc.com/news/b"),
                Story(source="hn", title="C", url="https://openai.com/blog"),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 3),
            stories=[
                Story(
                    source="arxiv", title="P1", url="https://a.com/1", category="cs.LG"
                ),
                Story(
                    source="arxiv", title="P2", url="https://b.com/2", category="cs.LG"
                ),
                Story(
                    source="arxiv", title="P3", url="https://c.com/3", category="cs.AI"
                ),
            ],
        ),
        tmp_path,
    )

    domains = top_domains(tmp_path)
    assert domains[0] == ("bbc.com", 2)
    assert ("openai.com", 1) in domains
    assert arxiv_category_counts(tmp_path) == [("cs.LG", 2), ("cs.AI", 1)]
    assert days_archiving(tmp_path) == 1


def test_fetch_health_compares_actual_to_expected(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 4),
            stories=[Story(source="hn", title="B", url="https://b")],
        ),
        tmp_path,
    )

    health = fetch_health(tmp_path)
    by_source = {row["source"]: row for row in health}
    assert "hn" in by_source
    assert by_source["hn"]["actual"] == 2
    assert by_source["hn"]["expected"] >= 2
    assert by_source["hn"]["rate"] == 100.0
    assert by_source["hn"]["last_fetched"] == date(2026, 8, 4)
    assert all(
        row["source"] in {"hn", "arxiv", "github", "registerspill"} for row in health
    )


def test_stats_page_and_trends_endpoint(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 10),
            stories=[
                Story(
                    source="arxiv",
                    title="Paper",
                    url="https://arxiv.org/abs/2607.1",
                    category="cs.LG",
                )
            ],
        ),
        tmp_path,
    )

    page = client.get("/stats/").text
    assert "Stories per week" in page
    assert 'class="trend-chart"' in page
    assert "<summary>More detail</summary>" in page
    assert "Top domains" in page
    assert "arxiv.org" in page
    assert "arXiv categories" in page
    assert "cs.LG" in page
    assert "Fetch health" in page
    assert "Days archiving" in page
    assert "View data table" in page
    assert "stat-table--trends" in page

    trends = client.get("/api/trends.json").json()
    assert [r["week"] for r in trends] == ["2026-W32", "2026-W33"]
    assert trends[0]["counts"]["hn"] == 1

    page = client.get("/").text
    assert 'id="export-saved"' in page
