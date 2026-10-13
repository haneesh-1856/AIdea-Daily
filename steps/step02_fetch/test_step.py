import json
import shutil
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from steps.testkit import make_root
from sqlalchemy import select

from common import db, runlog
from common.settings import ROOT, database_url
from steps.step01_start.step import start
from steps.step02_fetch import step
from steps.step02_fetch.step import FetchError, fetch

DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)

SOURCES = """
[settings]
max_age_days = 3
hn_min_points = 50
ai_keywords = ["ai"]

[[feed]]
name = "Lab Blog"
kind = "primary"
url = "https://lab.example/rss.xml"

[[feed]]
name = "Daily Press"
kind = "press"
general = true
url = "https://press.example/feed"

[[feed]]
name = "Quiet Lab"
kind = "primary"
type = "sitemap"
url = "https://quiet.example/sitemap.xml"
path_prefix = "/news/"

[[feed]]
name = "Bench Updates"
kind = "primary"
type = "listing"
only = "update"
url = "https://bench.example/updates"
"""
LISTING = (
    '<astro-island props="{&quot;articles&quot;:[1,[[0,{&quot;title&quot;:[0,&quot;Lab&#39;s Orion 4 evaluated&quot;],'
    '&quot;source&quot;:[0,&quot;Bench&quot;],&quot;link&quot;:[0,&quot;/models/orion-4&quot;],&quot;type&quot;:[0,&quot;update&quot;],'
    '&quot;date&quot;:[0,&quot;10/05/2026&quot;],&quot;heroImage&quot;:[0]}],[0,{&quot;title&quot;:[0,&quot;A paper wrote about us&quot;],'
    '&quot;source&quot;:[0,&quot;Daily Press&quot;],&quot;link&quot;:[0,&quot;https://press.example/about-bench&quot;],'
    '&quot;type&quot;:[0,&quot;news&quot;],&quot;date&quot;:[0,&quot;10/04/2026&quot;]}]]]}"></astro-island>'
)


def rss(*titles):
    items = "".join(
        f"<item><title>{t}</title><link>https://site.example/{n}</link>"
        f"<description>&lt;p&gt;About {t}&lt;/p&gt;</description>"
        f"<pubDate>{format_datetime(NOW - timedelta(hours=n))}</pubDate></item>"
        for n, t in enumerate(titles, 1)
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'


def sitemap(*pages):
    urls = "".join(f"<url><loc>{loc}</loc><lastmod>{when.isoformat()}</lastmod></url>" for loc, when in pages)
    return f"<urlset>{urls}</urlset>"


class Reply:
    def __init__(self, text="", data=None):
        self.text, self.content, self.data = text, text.encode(), data

    def json(self):
        return self.data


@pytest.fixture
def root(tmp_path, monkeypatch):
    make_root(tmp_path, monkeypatch)
    (tmp_path / "sources.toml").write_text(SOURCES, encoding="utf-8")
    return tmp_path


@pytest.fixture
def web(monkeypatch):
    """A fake internet: address -> Reply, or an exception to raise. Records every address asked for."""
    pages = {
        "https://lab.example/rss.xml": Reply(rss("New model", "New paper")),
        "https://press.example/feed": Reply(rss("AI funding round")),
        "https://quiet.example/sitemap.xml": Reply(
            sitemap(
                ("https://quiet.example/news/launch", NOW - timedelta(days=1)),
                ("https://quiet.example/news/old", NOW - timedelta(days=30)),
                ("https://quiet.example/careers/engineer", NOW - timedelta(days=1)),
                ("https://quiet.example/news/", NOW - timedelta(days=1)),
            )
        ),
        "https://quiet.example/news/launch": Reply(
            '<meta property="og:title" content="Launch &amp; more">'
            '<meta property="og:description" content="What launched">'
            '<meta property="article:published_time" content="2026-10-05T09:00:00Z">'
        ),
        "https://bench.example/updates": Reply(LISTING),
        step.HN_SEARCH: Reply(
            data={"hits": [
                {"objectID": "1", "title": "Show HN: an AI thing", "url": "https://hn.example/a", "created_at_i": 1791201600, "points": 120, "num_comments": 40},
                {"objectID": "2", "title": "Ask HN: no link", "url": None, "created_at_i": 1791201600, "points": 60, "num_comments": 5},
            ]}
        ),
    }
    asked = []

    def fake_get(url, params=None):
        asked.append(url)
        reply = pages.get(url, httpx.ConnectError("no route"))
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(step, "get", fake_get)
    pages["asked"] = asked
    return pages


def run(root):
    return fetch(DAY, root=root, now=NOW)


def health_rows(root):
    with db.connect(database_url(root)).connect() as conn:
        return {row.source: row for row in conn.execute(select(db.source_health))}


def test_fetch_reads_every_source_and_marks_step_two_done(root, web):
    started = start(DAY, root=root, checks=[])
    result = run(root)

    assert result.state == "fetched"
    by_source = {}
    for entry in result.entries:
        by_source.setdefault(entry["source"], []).append(entry)
    assert {name: len(found) for name, found in by_source.items()} == {
        "Lab Blog": 2, "Daily Press": 1, "Quiet Lab": 1, "Bench": 1, "Hacker News": 2,
    }
    assert by_source["Daily Press"][0]["general"] is True
    assert by_source["Lab Blog"][0]["general"] is False
    # Entries are raw: HTML is left for step 3 to strip.
    assert by_source["Lab Blog"][0]["summary"] == "<p>About New model</p>"

    assert json.loads(result.entries_file.read_text(encoding="utf-8"))["entries"] == result.entries
    assert all(row.ok for row in health_rows(root).values())
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.next_step(conn, started.run_id) == 3


def test_sitemap_reads_only_recent_pages_under_its_prefix(root, web):
    start(DAY, root=root, checks=[])
    entry = next(e for e in run(root).entries if e["source"] == "Quiet Lab")

    assert entry["title"] == "Launch & more"
    assert entry["summary"] == "What launched"
    assert entry["published_at"] == "2026-10-05T09:00:00+00:00"
    assert [url for url in web["asked"] if "quiet.example/" in url and "sitemap" not in url] == [
        "https://quiet.example/news/launch"
    ]


def test_a_listing_page_gives_its_entries_of_one_type_credited_to_the_outlet_it_names(root, web):
    start(DAY, root=root, checks=[])
    result = run(root)
    entry = next(e for e in result.entries if e["source"] == "Bench")

    assert (entry["title"], entry["url"]) == ("Lab's Orion 4 evaluated", "https://bench.example/models/orion-4")
    assert entry["published_at"] == "2026-10-05T00:00:00+00:00" and entry["kind"] == "primary"
    assert not any(e["title"] == "A paper wrote about us" for e in result.entries)  # another type of entry
    assert health_rows(root)["Bench Updates"].entries == 1  # the source is recorded under its own name


def test_hacker_news_keeps_points_and_falls_back_to_the_discussion_link(root, web):
    start(DAY, root=root, checks=[])
    linked, unlinked = [e for e in run(root).entries if e["source"] == "Hacker News"]

    assert (linked["url"], linked["points"], linked["comments"]) == ("https://hn.example/a", 120, 40)
    assert unlinked["url"] == unlinked["discussion_url"] == "https://news.ycombinator.com/item?id=2"


def test_a_failed_source_is_recorded_and_the_run_continues(root, web):
    web["https://press.example/feed"] = httpx.ConnectError("no route")
    web["https://lab.example/rss.xml"] = Reply("this is not a feed")
    start(DAY, root=root, checks=[])
    result = run(root)

    assert {e["source"] for e in result.entries} == {"Quiet Lab", "Bench", "Hacker News"}
    rows = health_rows(root)
    assert (rows["Daily Press"].ok, rows["Daily Press"].error) == (False, "ConnectError: no route")
    assert rows["Lab Blog"].ok is False
    assert rows["Quiet Lab"].ok is True
    assert "| Daily Press | 1 | ConnectError: no route |" in result.report.read_text(encoding="utf-8")


def test_a_source_slower_than_the_limit_is_abandoned(root, web, monkeypatch):
    fake_get = step.get

    def slow_get(url, params=None):
        if "press.example" in url:
            time.sleep(1)
        return fake_get(url, params)

    monkeypatch.setattr(step, "get", slow_get)
    monkeypatch.setattr(step, "TIMEOUT", 0.3)
    start(DAY, root=root, checks=[])
    began = time.monotonic()
    result = run(root)

    assert time.monotonic() - began < 0.9
    assert "Daily Press" not in {e["source"] for e in result.entries}
    assert health_rows(root)["Daily Press"].error == "abandoned after 0.3 seconds"
    assert health_rows(root)["Lab Blog"].ok is True


def test_a_source_failing_on_several_runs_shows_its_streak(root, web):
    web["https://press.example/feed"] = httpx.ConnectError("no route")
    start(DAY, root=root, checks=[])
    run(root)
    start(DAY, root=root, checks=[], force=True)
    result = run(root)

    assert "| Daily Press | 2 | ConnectError: no route |" in result.report.read_text(encoding="utf-8")


def test_every_source_failing_stops_the_run(root, web):
    for url in list(web):
        web[url] = httpx.ConnectError("no route")
    started = start(DAY, root=root, checks=[])

    with pytest.raises(FetchError, match="Every source failed"):
        run(root)
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.next_step(conn, started.run_id) == 2
        assert conn.execute(select(db.run_steps.c.status).where(db.run_steps.c.step == 2)).scalar() == "failed"


def test_fetch_needs_step_one_first(root, web):
    with pytest.raises(FetchError, match="Run step 1 first"):
        run(root)
    assert web["asked"] == []


def test_a_second_call_does_not_fetch_again(root, web):
    start(DAY, root=root, checks=[])
    first = run(root)
    web["asked"].clear()
    second = run(root)

    assert second.state == "already_done"
    assert second.entries == first.entries
    assert web["asked"] == []
