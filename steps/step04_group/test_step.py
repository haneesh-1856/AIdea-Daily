import math
import shutil
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from steps.testkit import make_root
from sqlalchemy import select

from common import db, items, model, runlog
from common.settings import ROOT, database_url
from steps.step01_start.step import start
from steps.step04_group.step import GroupError, group, versions_of

DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path, monkeypatch):
    return make_root(tmp_path, monkeypatch)


def item(source, page, *, kind="press", links=(), title=None):
    link = f"https://{page}"
    return {"source": source, "kind": kind, "title": title or f"{source} on {page}", "url": link,
            "canonical_url": link, "links": [f"https://{target}" for target in links]}


def meaning(marks=None):
    """A stand-in for the local model. Texts are unrelated in meaning unless marked:
    marks maps a piece of a title to (subject, how alike two texts on that subject are)."""
    marks = marks or {}

    def embed(texts):
        subjects = sorted({subject for subject, _ in marks.values()})
        vectors = np.zeros((len(texts), len(subjects) + len(texts)))
        for row, text in enumerate(texts):
            subject, alike = next((mark for piece, mark in marks.items() if piece in text), (None, 0))
            if subject:
                vectors[row, subjects.index(subject)] = math.sqrt(alike)
            vectors[row, len(subjects) + row] = math.sqrt(1 - alike)
        return vectors

    return embed


def stored(root, found, day=DAY):
    """Stands in for steps 1 to 3: opens the run, stores the items, marks steps 2 and 3 done."""
    started = start(day, root=root, checks=[])
    fetched_at = NOW + timedelta(days=(day - DAY).days)
    with db.connect(database_url(root)).begin() as conn:
        for one in found:
            items.upsert(conn, started.run_id, {**one, "fetched_at": fetched_at})
        for step in (2, 3):
            runlog.begin_step(conn, started.run_id, step)
            runlog.finish_step(conn, started.run_id, step)
    return started


def run(root, day=DAY, marks=None, ask=None):
    return group(day, root=root, embed=meaning(marks), ask=ask)


def grouped(root):
    """Every story as (title, [(source, matched_by), ...])."""
    query = (
        select(db.stories.c.id, db.stories.c.title, db.items.c.source, db.story_items.c.matched_by)
        .select_from(db.stories.join(db.story_items).join(db.items))
        .order_by(db.stories.c.id, db.items.c.id)
    )
    found = {}
    with db.connect(database_url(root)).connect() as conn:
        for row in conn.execute(query):
            found.setdefault(row.id, (row.title, []))[1].append((row.source, row.matched_by))
    return list(found.values())


def table(root, which):
    with db.connect(database_url(root)).connect() as conn:
        return conn.execute(select(which)).all()


def answering(same_event, seen=None):
    def ask(settings, system, user, schema):
        if seen is not None:
            seen.append(user)
        return model.Reply({"same_event": same_event}, "test-model", 100, 5, 0.001)

    return ask


# --- Layer 1: certain ---

def test_unrelated_items_each_become_a_story(root):
    started = stored(root, [item("Press A", "a.example/1"), item("Press B", "b.example/2")])
    result = run(root)

    assert (result.state, result.items, result.new_stories, result.joined) == ("grouped", 2, 2, 0)
    assert grouped(root) == [
        ("Press A on a.example/1", [("Press A", "new")]),
        ("Press B on b.example/2", [("Press B", "new")]),
    ]
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.next_step(conn, started.run_id) == 5


def test_the_same_link_from_two_sources_is_one_story_titled_by_the_primary_source(root):
    stored(root, [
        item("Hacker News", "lab.example/launch", kind="traction"),
        item("Lab", "lab.example/launch", kind="primary", title="Lab launches a model"),
    ])
    run(root)

    assert grouped(root) == [("Lab launches a model", [("Hacker News", "link"), ("Lab", "new")])]


def test_an_item_that_links_to_another_sources_article_joins_its_story(root):
    stored(root, [
        item("Lab", "lab.example/launch", kind="primary"),
        item("Blogger", "blog.example/thoughts", kind="newsletter", links=["lab.example/launch", "elsewhere.example/x"]),
    ])
    result = run(root)

    assert grouped(root) == [("Lab on lab.example/launch", [("Lab", "new"), ("Blogger", "mention")])]
    assert "- Blogger: [Blogger on blog.example/thoughts](https://blog.example/thoughts) (one links to the other)" in (
        result.report.read_text(encoding="utf-8")
    )


def test_a_digest_linking_to_several_stories_joins_none(root):
    stored(root, [
        item("Lab", "lab.example/launch", kind="primary"),
        item("Rival", "rival.example/reply", kind="primary"),
        item("Digest", "digest.example/weekly", kind="newsletter", links=["lab.example/launch", "rival.example/reply"]),
    ])
    result = run(root)

    assert result.new_stories == 3
    assert "- Digest: Digest on digest.example/weekly" in result.report.read_text(encoding="utf-8")


def test_a_source_linking_to_its_own_post_does_not_merge_them(root):
    stored(root, [
        item("Blogger", "blog.example/first", kind="newsletter"),
        item("Blogger", "blog.example/second", kind="newsletter", links=["blog.example/first"]),
    ])
    assert run(root).new_stories == 2


def test_a_later_item_joins_the_story_from_an_earlier_day(root):
    stored(root, [item("Lab", "lab.example/launch", kind="primary")])
    run(root)
    next_day = date(2026, 10, 7)
    stored(root, [item("Hacker News", "lab.example/launch", kind="traction")], day=next_day)
    result = run(root, next_day)

    assert (result.new_stories, result.joined) == (0, 1)
    assert grouped(root) == [("Lab on lab.example/launch", [("Lab", "new"), ("Hacker News", "link")])]


def test_a_story_older_than_the_age_limit_gains_nothing(root):
    stored(root, [item("Lab", "lab.example/launch", kind="primary")])
    run(root)
    later = date(2026, 10, 12)
    stored(root, [item("Hacker News", "lab.example/launch", kind="traction")], day=later)

    assert run(root, later).new_stories == 1


def test_two_existing_stories_are_never_merged(root):
    stored(root, [item("Lab", "lab.example/launch", kind="primary"), item("Rival", "rival.example/reply", kind="primary")])
    run(root)
    next_day = date(2026, 10, 7)
    # Shares a link with the first story and links to the second.
    stored(root, [item("Hacker News", "lab.example/launch", kind="traction", links=["rival.example/reply"])], day=next_day)
    run(root, next_day)

    assert grouped(root) == [
        ("Lab on lab.example/launch", [("Lab", "new"), ("Hacker News", "link")]),
        ("Rival on rival.example/reply", [("Rival", "new")]),
    ]


# --- Layer 2: likely ---

BEAM = [
    item("Press A", "a.example/beam", title="Reflection debuts Beam, an open model"),
    item("Press B", "b.example/beam", title="Why Beam from Reflection matters"),
]


def test_items_alike_in_meaning_that_share_a_name_are_merged(root):
    stored(root, BEAM)
    result = run(root, marks={"Beam": ("beam", 0.9)})

    assert result.uncertain == 0
    assert grouped(root) == [("Reflection debuts Beam, an open model", [("Press A", "new"), ("Press B", "similarity")])]


@pytest.mark.parametrize("found, why", [
    ([item("Press A", "a.example/1", title="Lab spending keeps climbing"),
      item("Press B", "b.example/2", title="Costs of training are soaring")], "no shared distinctive name"),
    ([item("Press A", "a.example/1", title="Reflection debuts Beam"),
      item("Press A", "a.example/2", title="Inside the making of Beam")], "same source"),
    ([item("Press A", "a.example/1", title="Lab ships Orion 4 today"),
      item("Press B", "b.example/2", title="Orion 5 arrives from Lab")], "different version numbers"),
])
def test_a_rule_can_stop_an_automatic_merge_however_alike_the_items_are(root, found, why):
    stored(root, found)
    result = run(root, marks={one["title"]: ("same", 0.95) for one in found})

    assert (result.new_stories, result.uncertain) == (2, 1)
    logged, = table(root, db.judge_log)
    assert (logged.why_uncertain, logged.answer, round(logged.similarity, 2)) == (why, "not asked", 0.95)


def test_items_below_the_judging_threshold_are_simply_apart(root):
    stored(root, BEAM)
    result = run(root, marks={"Beam": ("beam", 0.7)})

    assert (result.new_stories, result.uncertain) == (2, 0)
    assert table(root, db.judge_log) == []


# --- Layer 3: uncertain ---

def test_the_model_settles_a_pair_in_the_middle_band_and_sees_only_that_pair(root):
    seen = []
    started = stored(root, BEAM + [item("Press C", "c.example/other", title="Something else entirely")])
    result = run(root, marks={"Beam": ("beam", 0.78)}, ask=answering(True, seen))

    assert grouped(root)[0] == ("Reflection debuts Beam, an open model", [("Press A", "new"), ("Press B", "judge")])
    assert result.new_stories == 2
    assert len(seen) == 1 and "Reflection debuts Beam" in seen[0] and "Something else" not in seen[0]
    logged, = table(root, db.judge_log)
    assert (logged.why_uncertain, logged.answer) == ("in the middle band", "yes")
    call, = table(root, db.model_calls)
    assert (call.run_id, call.step, call.purpose, call.tokens_in, call.cost) == (started.run_id, 4, "judge", 100, 0.001)


def test_a_no_keeps_the_stories_apart_but_links_them_in_a_thread(root):
    stored(root, BEAM)
    run(root, marks={"Beam": ("beam", 0.78)}, ask=answering(False))

    assert len(grouped(root)) == 2
    first, second = table(root, db.stories)
    assert first.thread_id is not None and first.thread_id == second.thread_id
    assert table(root, db.threads)[0].title == "Reflection debuts Beam, an open model"


def test_a_failed_model_request_leaves_the_pair_apart(root):
    def failing(settings, system, user, schema):
        raise model.ModelError("rate limit")

    stored(root, BEAM)
    result = run(root, marks={"Beam": ("beam", 0.78)}, ask=failing)

    assert result.new_stories == 2
    assert table(root, db.judge_log)[0].answer == "failed"
    assert table(root, db.model_calls) == []


def test_no_more_pairs_are_judged_than_the_ceiling_allows(root):
    seen = []
    path = root / "settings.toml"
    path.write_text(path.read_text(encoding="utf-8").replace("max_judge_pairs = 60", "max_judge_pairs = 1"), encoding="utf-8")
    stored(root, BEAM + [item("Press C", "c.example/beam", title="Beam, explained")])
    run(root, marks={"Beam": ("beam", 0.78)}, ask=answering(False, seen))

    assert len(seen) == 1
    assert sorted(row.answer for row in table(root, db.judge_log)) == ["no", "not asked", "not asked"]


@pytest.mark.parametrize("title, versions", [
    ("Introducing Mistral Large 4", {"4"}),
    ("GPT-5.4 nano beats GPT-5.5", {"5.4", "5.5"}),
    ("Lambda to raise $4B in 2026, up 30%", set()),
    ("Reflection Beam - 501B-A23B, a 1T model", set()),
    ("Import AI 475, out 2026-10-06", set()),
])
def test_version_numbers_are_told_from_other_numbers(title, versions):
    assert versions_of(title) == versions


# --- The step as a whole ---

def test_it_needs_step_three_first(root):
    start(DAY, root=root, checks=[])
    with pytest.raises(GroupError, match="Run step 3 first"):
        run(root)


def test_a_second_call_groups_nothing_again(root):
    stored(root, [item("Press A", "a.example/1")])
    run(root)
    assert run(root).state == "already_done"
    assert len(grouped(root)) == 1


def test_a_bare_number_or_a_weekday_is_not_a_name_two_items_can_share():
    from types import SimpleNamespace

    from steps.step04_group.step import names_of

    # "$1,000" and "129,000" both leave the piece "000". On 7 October 2026 that alone merged these two stories.
    credits = SimpleNamespace(title="Anthropic is giving startups a free year of Claude Team and $1,000 in credits", summary="")
    security = SimpleNamespace(title="Anthropic gives more security teams access to Claude",
                               summary="On Tuesday partners in its Cyber Verification Program found at least 129,000 flaws.")
    assert names_of(credits) == {"claude", "team"}
    assert names_of(security) == {"claude", "cyber", "verification", "program"}
    # A name with a digit in it is still a name.
    assert names_of(SimpleNamespace(title="Lab ships GPT-6 and Orion 4", summary="")) == {"gpt-6", "orion"}


def test_the_judge_is_shown_the_opening_of_each_article_and_what_was_read_is_kept(root):
    stored(root, [item("Lab", "lab.example/mission", kind="primary", title="Introducing the alpha mission"),
                  item("Press A", "a.example/scanner", title="Lab launches a free alpha scanner")])
    seen, asked = [], []

    def read(url):
        asked.append(url)
        return "ok", f"Today we are launching the scanner, at {url}. " + "More detail follows here. " * 100

    group(DAY, root=root, embed=meaning({"alpha": ("launch", 0.77)}), ask=answering(True, seen), read=read)

    # On 8 October 2026 the judge saw two headlines, one of which did not say what the post announced, and kept them apart.
    assert sorted(asked) == ["https://a.example/scanner", "https://lab.example/mission"]
    assert seen[0].count("Opening of the article: Today we are launching the scanner") == 2
    opening = seen[0].split("Opening of the article: ")[1].split("\n\n")[0]
    assert len(opening.split()) == 150  # the opening, not the whole article
    assert sorted((row.status, row.words > 150) for row in table(root, db.articles)) == [("ok", True), ("ok", True)]
    assert grouped(root)[0][1] == [("Lab", "new"), ("Press A", "judge")]


def test_an_article_already_stored_is_not_read_again_for_the_judge(root):
    from common import articles

    started = stored(root, [item("Lab", "lab.example/mission", kind="primary", title="Introducing the alpha mission"),
                            item("Press A", "a.example/scanner", title="Lab launches a free alpha scanner")])
    with db.connect(database_url(root)).begin() as conn:
        first = conn.execute(select(db.items.c.id).where(db.items.c.source == "Lab")).scalar()
        articles.save(conn, first, "ok", "Stored earlier. " * 60, NOW)
    seen, asked = [], []
    group(DAY, root=root, embed=meaning({"alpha": ("launch", 0.77)}), ask=answering(False, seen),
          read=lambda url: (asked.append(url), ("refused", None))[1])

    assert asked == ["https://a.example/scanner"] and started.run_id == 1
    # The stored article's opening is shown; the refused one has none, and its refusal is remembered.
    assert seen[0].count("Opening of the article:") == 1 and "Stored earlier." in seen[0]
    assert sorted(row.status for row in table(root, db.articles)) == ["ok", "refused"]


def test_an_item_taken_out_of_a_story_is_grouped_again_and_never_put_back_into_it(root):
    from common import stories

    started = stored(root, [
        item("Lab", "lab.example/launch", kind="primary"),
        item("Blogger", "blog.example/thoughts", kind="newsletter", links=["lab.example/launch"]),
    ])
    run(root)
    assert grouped(root) == [("Lab on lab.example/launch", [("Lab", "new"), ("Blogger", "mention")])]
    with db.connect(database_url(root)).begin() as conn:
        story_id = conn.execute(select(db.stories.c.id)).scalar()
        blogger = conn.execute(select(db.items.c.id).where(db.items.c.source == "Blogger")).scalar()
        lab = conn.execute(select(db.items.c.id).where(db.items.c.source == "Lab")).scalar()
        # A story is never emptied: asking for every item changes nothing.
        assert stories.split_off(conn, started.run_id, story_id, [blogger, lab], "x") == []
        assert stories.split_off(conn, started.run_id, story_id, [blogger], "the writer found it reports a different event") == [blogger]

    next_day = DAY + timedelta(days=1)
    stored(root, [], day=next_day)
    result = run(root, day=next_day)

    # Its link to the Lab article would have put it straight back. It becomes a story of its own instead.
    assert grouped(root) == [("Lab on lab.example/launch", [("Lab", "new")]), ("Blogger on blog.example/thoughts", [("Blogger", "new")])]
    assert (result.items, result.new_stories, result.joined) == (1, 1, 0)
    assert "1 of these items came back to be grouped again" in result.report.read_text(encoding="utf-8")
