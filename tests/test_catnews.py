from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import DATA_DIR
from app.fetchers.arxiv import parse_entry
from app.fetchers.github import parse_item
from app.fetchers.hn import parse_hit
from app.models import Digest, Story
from app.store import save_digest, site_stats

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
    story = parse_entry(root.find("atom:entry", ns))
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


def test_story_markdown_and_signal():
    story = Story(
        source="hn",
        title="T",
        url="https://example.com",
        byline="alice",
        why_read="Short.",
        signal="Must-Read",
    )
    md = story.to_markdown()
    assert "**Why read:** Short." in md
    assert "## [T](https://example.com)" in md


def test_digest_stats_and_store_roundtrip(tmp_path):
    digest = Digest(
        date=date(2026, 8, 2),
        stories=[
            Story(source="hn", title="A", url="https://a"),
            Story(source="hn", title="B", url="https://b"),
            Story(source="arxiv", title="C", url="https://c"),
        ],
    )
    path = save_digest(digest, tmp_path)
    assert path.exists()

    loaded = Digest.model_validate_json(path.read_text())
    assert loaded.stats == {"hn": 2, "arxiv": 1}

    stats = site_stats(tmp_path)
    assert stats.total_stories == 3
    assert stats.by_source == {"arxiv": 1, "hn": 2}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import main as app_main

    monkeypatch.setattr(app_main, "DATA_DIR", tmp_path)
    with TestClient(app_main.app) as c:
        yield c


def test_api_empty_returns_404(client):
    assert client.get("/api/digest").status_code == 404
    assert client.get("/").status_code == 404


def test_api_pages_and_filters(client, tmp_path):
    digest = Digest(
        date=date(2026, 8, 2),
        stories=[
            Story(source="hn", title="HN story", url="https://a", signal="Must-Read"),
            Story(source="arxiv", title="arXiv paper", url="https://b"),
        ],
    )
    save_digest(digest, tmp_path)

    assert client.get("/").status_code == 200
    assert client.get("/archive/").status_code == 200
    assert client.get("/stats/").status_code == 200
    assert client.get("/feed.rss").status_code == 200

    body = client.get("/api/stories", params={"source": "hn"}).json()
    assert [s["title"] for s in body] == ["HN story"]
    body = client.get("/api/stories", params={"signal": "Must-Read"}).json()
    assert len(body) == 1

    md = client.get("/api/stories.md").text
    assert "### 1. HN story" in md
