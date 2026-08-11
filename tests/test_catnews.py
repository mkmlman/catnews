from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.fetchers.arxiv import parse_entry
from app.fetchers.github import parse_item
from app.fetchers.hn import parse_hit
from app.fetchers.rss import parse_entry as parse_rss_entry
from app.fetchers.rss import parse_links, strip_html
from app.models import SourceSnapshot, Story
from app.store import (
    combined_digest,
    latest_stories_by_source,
    save_snapshot,
    site_stats,
    source_registry,
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
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2607.28628v1</id>
    <published>2026-07-29T17:00:00Z</published>
    <title>Learning to Trace Seiberg Dualities</title>
    <author><name>Jonathan J. Heckman</name></author>
    <author><name>Shani Meynet</name></author>
    <summary>We study tracing via local models.</summary>
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
    build_site(tmp_path, out, "/catnews", "https://example.com")

    app_static = Path(__file__).resolve().parent.parent / "app" / "static"
    for name in ("favicon.svg", "style.css"):
        assert (out / "static" / name).read_bytes() == (app_static / name).read_bytes()
    assert (out / "static" / "fonts").is_dir()
    assert (out / "static" / "favicon.svg").exists()


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
