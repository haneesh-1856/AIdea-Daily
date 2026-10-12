import json
import shutil
from datetime import date, datetime, timedelta, timezone

import pytest

from steps.testkit import make_root
from sqlalchemy import select

from common import db, runlog
from common.report import step_folder
from common.settings import ROOT, database_url
from steps.step01_start.step import start
from steps.step03_clean_store.step import CleanError, canonical_url, clean_store

DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path, monkeypatch):
    return make_root(tmp_path, monkeypatch)


def entry(title="OpenAI ships a model", url="https://site.example/a", *, source="Lab Blog", kind="primary",
          general=False, summary=None, age_days=1, **extra):
    published = (NOW - timedelta(days=age_days)).isoformat() if age_days is not None else None
    return {"source": source, "kind": kind, "general": general, "title": title, "url": url,
            "summary": summary, "published_at": published, **extra}


def fetched(root, entries, day=DAY, **kwargs):
    """Stands in for steps 1 and 2: opens the run, leaves the entries file, marks step 2 done."""
    started = start(day, root=root, checks=[], **kwargs)
    (step_folder(root, day, 2) / "entries.json").write_text(
        json.dumps({"fetched_at": NOW.isoformat(), "entries": entries}), encoding="utf-8"
    )
    with db.connect(database_url(root)).begin() as conn:
        runlog.begin_step(conn, started.run_id, 2)
        runlog.finish_step(conn, started.run_id, 2)
    return started


def stored(root):
    with db.connect(database_url(root)).connect() as conn:
        return conn.execute(select(db.items).order_by(db.items.c.id)).all()


def test_an_entry_is_cleaned_and_stored(root):
    started = fetched(root, [entry(
        "New &amp; <b>improved</b>", "http://www.Site.example/post/?utm_source=x&id=7#top",
        summary="<p>First   line</p><p>Second</p>",
    )])
    result = clean_store(DAY, root=root)

    assert (result.state, result.kept, result.new) == ("stored", 1, 1)
    item, = stored(root)
    assert item.title == "New & improved"
    assert item.summary == "First line Second"
    assert item.canonical_url == "https://site.example/post?id=7"
    assert item.url == "http://www.Site.example/post/?utm_source=x&id=7#top"
    assert item.run_id == started.run_id
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.next_step(conn, started.run_id) == 4


def test_links_inside_the_description_are_kept_for_grouping(root):
    fetched(root, [entry(
        url="https://site.example/a",
        summary='See <a href="https://www.other.example/post/?utm_source=x">this</a>, '
                '<a href="https://site.example/a">this page</a> and <a href="/relative">that</a>.',
    )])
    clean_store(DAY, root=root)

    with db.connect(database_url(root)).connect() as conn:
        assert [row.canonical_url for row in conn.execute(select(db.item_links))] == ["https://other.example/post"]
    assert stored(root)[0].summary == "See this , this page and that ."


def test_old_entries_are_dropped_and_undated_ones_kept(root):
    fetched(root, [
        entry(url="https://site.example/recent", age_days=2),
        entry(url="https://site.example/old", age_days=4),
        entry(url="https://site.example/undated", age_days=None),
    ])
    clean_store(DAY, root=root)

    assert [(item.canonical_url, item.published_at is None) for item in stored(root)] == [
        ("https://site.example/recent", False),
        ("https://site.example/undated", True),
    ]


def test_general_entries_must_match_an_ai_keyword(root):
    fetched(root, [
        entry("Quarterly results", "https://site.example/1", general=True),
        entry("Quarterly results", "https://site.example/2", general=True, summary="Driven by Claude demand"),
        entry("Painting the office", "https://site.example/3", general=True),
        # "ai" inside another word is not a match
        entry("Maintaining old code", "https://site.example/4", general=True),
        entry("Quarterly results", "https://site.example/5"),
    ])
    result = clean_store(DAY, root=root)

    assert [item.canonical_url[-1] for item in stored(root)] == ["2", "5"]
    assert "| Lab Blog | 5 | 0 | 3 | 2 | 2 |" in result.report.read_text(encoding="utf-8")


def test_a_general_entry_linking_to_a_sources_article_is_kept_without_a_keyword(root):
    hn = dict(source="Hacker News", kind="traction", general=True)
    fetched(root, [entry("Our approach to text provenance", "https://lab.example/provenance")])
    clean_store(DAY, root=root)
    next_day = date(2026, 10, 7)
    fetched(root, [
        entry("Our approach to text provenance", "https://lab.example/provenance/", **hn),  # stored on an earlier day
        entry("Quarterly results", "https://lab.example/results"),
        entry("Quarterly results", "https://www.lab.example/results?utm_source=hn", **hn),  # in the same batch
        entry("Painting the office", "https://elsewhere.example/paint", **hn),
    ], day=next_day)
    clean_store(next_day, root=root)

    assert [item.canonical_url for item in stored(root) if item.source == "Hacker News"] == [
        "https://lab.example/provenance", "https://lab.example/results",
    ]


def test_one_article_is_stored_once_per_source(root):
    fetched(root, [
        entry(url="https://site.example/a"),
        entry(url="https://www.site.example/a/?utm_medium=rss"),
        entry(url="https://site.example/a", source="Daily Press", kind="press"),
    ])
    result = clean_store(DAY, root=root)

    assert (result.kept, result.new) == (3, 2)
    assert [item.source for item in stored(root)] == ["Lab Blog", "Daily Press"]


def test_a_later_run_refreshes_points_without_storing_the_item_again(root):
    hn = dict(source="Hacker News", kind="traction", general=True, discussion_url="https://news.ycombinator.com/item?id=1")
    fetched(root, [entry(points=60, comments=5, **hn)])
    clean_store(DAY, root=root)
    next_day = date(2026, 10, 7)
    fetched(root, [entry(points=300, comments=90, **hn)], day=next_day)
    result = clean_store(next_day, root=root)

    assert (result.kept, result.new) == (1, 0)
    item, = stored(root)
    assert (item.points, item.comments) == (300, 90)


def test_it_needs_step_two_first(root):
    start(DAY, root=root, checks=[])
    with pytest.raises(CleanError, match="Run step 2 first"):
        clean_store(DAY, root=root)


def test_a_second_call_stores_nothing_again(root):
    fetched(root, [entry()])
    clean_store(DAY, root=root)
    assert clean_store(DAY, root=root).state == "already_done"
    assert len(stored(root)) == 1


@pytest.mark.parametrize("url, expected", [
    ("https://www.example.com/a/", "https://example.com/a"),
    ("http://example.com/a?utm_campaign=x&fbclid=y", "https://example.com/a"),
    ("https://example.com/a?page=2&ref=hn", "https://example.com/a?page=2"),
    ("https://example.com/a#comments", "https://example.com/a"),
    ("https://example.com/a/\\", "https://example.com/a"),
])
def test_canonical_url(url, expected):
    assert canonical_url(url) == expected


def test_a_keyword_followed_by_a_hyphen_or_a_digit_is_still_a_match(root):
    fetched(root, [
        entry("GPT-6 is here", "https://site.example/1", general=True),
        entry("AI-assisted proof of optimal packing for 11 squares", "https://site.example/2", general=True),
        entry("Qwen3 Max weights", "https://site.example/3", general=True),
        # a keyword inside a longer word, or after a hyphen, is still not one
        entry("Maintaining old code", "https://site.example/4", general=True),
        entry("A semi-ai approach to gardening", "https://site.example/5", general=True),
    ])
    clean_store(DAY, root=root)

    assert [item.canonical_url[-1] for item in stored(root)] == ["1", "2", "3"]


def test_the_extra_words_keep_an_entry_and_are_not_added_to_the_keywords_grouping_uses(root):
    from common.settings import SettingsError, load

    fetched(root, [
        entry("I gave Opus 5.5 one prompt and six hours", "https://site.example/1", general=True),
        entry('Senator says "artificial intelligence" needs rules', "https://site.example/2", general=True),
        entry("Painting the office", "https://site.example/3", general=True),
    ])
    clean_store(DAY, root=root)

    assert [item.canonical_url[-1] for item in stored(root)] == ["1", "2"]
    # Step 4 treats every AI keyword as too common to identify a story, so a product's name must not be among them.
    collect = load(root)["collect"]
    assert "opus" in collect["also_keep"] and not set(collect["also_keep"]) & set(collect["ai_keywords"])

    path = root / "sources.toml"
    path.write_text(path.read_text(encoding="utf-8").replace("also_keep = [", 'also_keep = [7, ', 1), encoding="utf-8")
    with pytest.raises(SettingsError, match="also_keep must be a list"):
        load(root)


def test_a_run_started_before_the_extra_words_existed_still_filters():
    from steps.step03_clean_store.step import about_ai_pattern

    pattern = about_ai_pattern({"ai_keywords": ["ai", "gpt"]})
    assert pattern.search("GPT-6 is here") and not pattern.search("Opus 5.5 visualises a novel")
