from datetime import timedelta

import pytest

from common import db, model, runlog
from common.settings import database_url
from steps.step05_score.step import score
from steps.step06_select.step import select
from steps.step07_plan.step import plan
from steps.step08_write.step import WriteError, write
from steps.testkit import (
    DAY, FILLER, LINKING, MORE, NOW, STORY, article, edit_settings, fake_web, grouped, item, link_of, make_root, rater, rows, writer,
)

STRONG = [item("Lab", "primary", summary="Lab says the thing is ready."), item("Press A"), item("Press B")]


@pytest.fixture
def root(tmp_path, monkeypatch):
    return make_root(tmp_path, monkeypatch)


def planned(root, day=DAY):
    score(day, root=root, ask=rater())
    select(day, root=root, now=NOW)
    return plan(day, root=root)


def script_of(root, run_id):
    """[(part, story title or None, text)] in speaking order."""
    titles = {row.id: row.title for row in rows(root, db.stories)}
    found = sorted(rows(root, db.script_lines, run_id=run_id), key=lambda row: row.position)
    return [(row.part, titles.get(row.story_id), row.text) for row in found]


def test_a_story_is_written_stored_and_laid_out_one_sentence_per_line(root, monkeypatch):
    fake_web(monkeypatch, {link_of("Lab", "launch"): article("Lab released Orion 4 with 12 billion parameters.", FILLER, MORE)})
    grouped(root, {"launch": STRONG})
    planned(root)
    fake = writer()
    result = write(DAY, root=root, ask=fake)

    assert (result.state, result.written, result.set_aside, result.cost) == ("written", 1, 0, 0.004)
    assert script_of(root, result.run_id) == [
        ("opening", None, "Good morning."),
        ("opening", None, "Here is the AI news."),
        ("headline", "launch", "Lab ships a thing."),
        ("title", "launch", "launch."),
        ("what", "launch", "Lab shipped a thing."),
        ("what", "launch", "It is available now."),
        ("how", "launch", "Press B disagrees."),
        ("brief", "launch", "Lab shipped a thing."),
        ("closing", None, "That is all for today."),
    ]
    summary, = rows(root, db.summaries, run_id=result.run_id)
    assert (summary.flag, summary.what_happened) == (None, "Lab shipped a thing. It is available now.")
    assert [(call.purpose, call.step, call.cost) for call in rows(root, db.model_calls, step=8)] == [("story", 8, 0.002), ("linking", 8, 0.002)]


def test_coverage_broadly_agrees_is_not_put_in_the_script(root, monkeypatch):
    fake_web(monkeypatch, {link_of("Lab", "launch"): article("Lab released Orion 4 with 12 billion parameters.", FILLER, MORE)})
    grouped(root, {"launch": STRONG})
    planned(root)
    result = write(DAY, root=root, ask=writer({"launch": {**STORY, "how_sources_see_it": "Coverage broadly agrees."}}))

    assert [part for part, _, _ in script_of(root, result.run_id)] == ["opening", "opening", "headline", "title", "what", "what", "brief", "closing"]


def test_the_model_is_given_the_rules_the_label_and_each_sources_text(root, monkeypatch):
    fake_web(monkeypatch, {link_of("Lab", "launch"): article("Lab released Orion 4 with 12 billion parameters.", FILLER, MORE)})
    edit_settings(root, "max_source_words = 1200", "max_source_words = 20")
    grouped(root, {"launch": STRONG})
    planned(root)
    fake = writer()
    write(DAY, root=root, ask=fake)

    rules, material = fake.requests[0]
    assert "Use only the source texts in the message" in rules and "than 600 words in all" in rules
    assert "The episode has 1 stories, and this one has room for about 600 words" in rules
    assert material.startswith("Story: launch\nKind: a new story\nConfidence label: confirmed")
    assert "Source 1: Lab (primary)" in material and "Source 3: Press B (press)" in material
    # The article is cut to the setting; a source whose page could not be read falls back to its description.
    lab_text = material.split("Text (full article):\n")[1].split("\n\nSource 2")[0]
    assert "Lab released Orion 4 with 12 billion parameters." in lab_text
    assert len(lab_text.split()) == 20
    assert "the feed's short description only" in material
    # The linking request sees headlines and briefs, not the articles.
    assert "1. Lab ships a thing.\n   Brief: Lab shipped a thing." in fake.requests[1][1]
    assert "12 billion" not in fake.requests[1][1]


LENGTHS = {"long_from": 9.0, "long_words": 350, "medium_from": 8.0, "medium_words": 250, "short_from": 7.0, "short_words": 150,
           "quick_words": 70}


@pytest.mark.parametrize("score, segment, room", [
    (10.3, "main", (350, 455)), (9.0, "main", (350, 455)), (8.9, "main", (250, 325)), (7.0, "main", (150, 195)),
    (6.5, "quick_hits", (70, 91)),
    (9.5, "quick_hits", (70, 91)),  # an update, or a story with little to write from, is a quick hit whatever it scored
    (5.0, "corrections", (150, 195)), (9.5, "corrections", (350, 455)),  # a correction is never shorter than a short story
])
def test_how_long_a_story_runs_follows_its_score(score, segment, room):
    from types import SimpleNamespace

    from common import episodes
    settings = {"write": {"max_story_words": 600}, "lengths": LENGTHS}
    entry = SimpleNamespace(score=score, segment=segment)
    assert episodes.story_room(entry, settings, 5850, 20) == room  # (words to aim for, the most it may have)
    # No story is ever given more than the limit for one story.
    assert episodes.story_room(entry, {"write": {"max_story_words": 60}, "lengths": LENGTHS}, 5850, 20)[1] <= 60


def test_a_run_started_before_lengths_followed_the_score_shares_the_cap_equally():
    from types import SimpleNamespace

    from common import episodes
    entry = SimpleNamespace(score=8.0, segment="main")
    assert episodes.story_room(entry, {"write": {"max_story_words": 600}}, 2250, 8) == (230, 299)


def test_each_story_is_told_its_own_length(root, monkeypatch):
    fake_web(monkeypatch, {link_of("Lab", name): article("Lab released Orion 4 with 12 billion parameters.", FILLER, MORE)
                           for name in ("top", "middle", "small")})
    for key, value in LENGTHS.items():
        edit_settings(root, f"{key} = {'0.0' if key.endswith('from') else '600'}", f"{key} = {value}")
    grouped(root, {"top": STRONG, "middle": STRONG, "small": STRONG})
    score(DAY, root=root, ask=rater({"top": 10, "middle": 8, "small": 5}))
    select(DAY, root=root, now=NOW)
    planning = plan(DAY, root=root)
    fake = writer()
    write(DAY, root=root, ask=fake)

    told = {material.splitlines()[0].removeprefix("Story: "): rules for rules, material in fake.requests[:3]}
    assert "this one has room for about 350 words" in told["top"] and "than 455 words in all" in told["top"]
    assert "this one has room for about 250 words" in told["middle"]
    # Under the score for a short story it is a quick hit, and it is placed with the quick hits at the end.
    assert "this one has room for about 70 words" in told["small"]
    segments = {row.story_id: row.segment for row in rows(root, db.episode_stories)}
    titles = {row.id: row.title for row in rows(root, db.stories)}
    assert {titles[story_id]: segment for story_id, segment in segments.items()} == {"top": "main", "middle": "main", "small": "quick_hits"}
    assert "- small (new, confirmed, score 5, about 70 words" in planning.report.read_text(encoding="utf-8")


def test_the_intro_says_the_label_and_what_kind_of_story_it_is(root, monkeypatch):
    fake_web(monkeypatch)
    ids = grouped(root, {
        "written-up": [item("Press A"), item("Press B")],
        "chatter": [item("Hacker News", "traction", points=5000, comments=5000)],
        "saga": STRONG,
    })
    planned(root)
    first = write(DAY, root=root, ask=writer())
    next_day = DAY + timedelta(days=1)
    grouped(root, {"saga": [item("Press C"), item("Press D")]}, day=next_day, into=ids)
    planned(root, next_day)
    second = write(next_day, root=root, ask=writer())

    lines = script_of(root, first.run_id)
    # Every story's title is read before it.
    assert ("title", "written-up", "written-up.") in lines and ("title", "chatter", "chatter.") in lines
    # Nothing follows the title unless the listener needs it: here, only that one story is unconfirmed.
    assert [(title, text) for part, title, text in lines if part == "intro"] == [("chatter", "This one is unconfirmed.")]
    assert "confirmed, from" not in " ".join(text for _, _, text in lines)
    assert ("intro", "saga", "An update to a story covered before.") in script_of(root, second.run_id)


def test_the_intro_says_when_an_older_story_first_emerged(root, monkeypatch):
    fake_web(monkeypatch)
    ids = grouped(root, {"slow burn": STRONG})
    score(DAY, root=root, ask=rater(default=1))
    select(DAY, root=root, now=NOW)
    next_day = DAY + timedelta(days=1)
    grouped(root, {"slow burn": [item("Press C"), item("Press D")]}, day=next_day, into=ids)
    planned(root, next_day)
    result = write(next_day, root=root, ask=writer())

    assert ("intro", "slow burn", "This first emerged on Tuesday.") in script_of(root, result.run_id)


def test_an_update_is_given_what_was_already_reported_and_may_have_nothing_new(root, monkeypatch):
    fake_web(monkeypatch)
    ids = grouped(root, {"saga": STRONG})
    planned(root)
    write(DAY, root=root, ask=writer())
    next_day = DAY + timedelta(days=1)
    grouped(root, {"saga": [item("Press C"), item("Press D")]}, day=next_day, into=ids)
    planned(root, next_day)
    fake = writer({"saga": dict(STORY, nothing_new=True, note="Both articles repeat the launch.")})
    result = write(next_day, root=root, ask=fake)

    assert "Kind: an update to a story already reported" in fake.requests[0][1]
    assert "Already reported:\n- 2026-10-06: Lab shipped a thing. It is available now." in fake.requests[0][1]
    assert (result.written, result.set_aside) == (0, 1)
    summary, = rows(root, db.summaries, run_id=result.run_id)
    assert (summary.flag, summary.note, summary.what_happened) == ("nothing_new", "Both articles repeat the launch.", None)
    # With nothing left to say, no linking request is made and the script says so.
    assert len(fake.requests) == 1
    assert [text for _, _, text in script_of(root, result.run_id)] == [
        "This is your AI news briefing for Wednesday, 7 October 2026.", "No story met the bar today.", "That is all for today.",
    ]


def test_a_story_whose_sources_describe_different_events_is_set_aside(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"mixed": STRONG, "clean": STRONG})
    planned(root)
    result = write(DAY, root=root, ask=writer({"mixed": dict(STORY, different_events=True, note="One is a launch, one a lawsuit.")}))

    assert (result.written, result.set_aside) == (1, 1)
    assert {title for _, title, _ in script_of(root, result.run_id) if title} == {"clean"}
    assert "set aside: the sources describe different events (One is a launch, one a lawsuit.)" in result.report.read_text(encoding="utf-8")


def test_a_failed_request_sets_one_story_aside_and_the_rest_are_written(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"unlucky": STRONG, "fine": STRONG})
    planned(root)
    result = write(DAY, root=root, ask=writer({"unlucky": model.ModelError("rate limit")}))

    assert (result.written, result.set_aside) == (1, 1)
    flags = {row.flag: row.note for row in rows(root, db.summaries, run_id=result.run_id)}
    assert flags == {"failed": "rate limit", None: None}


def test_when_every_story_fails_the_step_fails_and_a_rerun_tries_again(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"launch": STRONG})
    started = planned(root)
    with pytest.raises(WriteError, match="failed on every story. The first error: rate limit"):
        write(DAY, root=root, ask=writer({"launch": model.ModelError("rate limit")}))
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.next_step(conn, started.run_id) == 8

    result = write(DAY, root=root, ask=writer())
    assert (result.written, [row.flag for row in rows(root, db.summaries, run_id=result.run_id)]) == (1, [None])


def test_a_run_that_stops_midway_keeps_what_was_written_and_does_not_pay_twice(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"first": STRONG, "second": [item("Press A"), item("Press B")]})
    planned(root)
    with pytest.raises(RuntimeError):
        write(DAY, root=root, ask=writer({"second": RuntimeError("the machine was switched off")}))

    fake = writer()
    result = write(DAY, root=root, ask=fake)
    assert result.written == 2
    assert [material.splitlines()[0] for _, material in fake.requests] == ["Story: second", "Date: Tuesday, 6 October 2026"]


def test_a_failed_linking_request_falls_back_to_a_plain_opening_and_closing(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"launch": STRONG})
    planned(root)
    result = write(DAY, root=root, ask=writer(linking=model.ModelError("overloaded")))

    lines = script_of(root, result.run_id)
    assert lines[0] == ("opening", None, "This is your AI news briefing for Tuesday, 6 October 2026.")
    assert lines[-1] == ("closing", None, "That is all for today.")
    assert "made by code, because the request for them failed: overloaded" in result.report.read_text(encoding="utf-8")


def test_without_a_model_the_run_stops_here_with_instructions(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"launch": STRONG})
    started = planned(root)
    with pytest.raises(WriteError, match="No model is chosen"):
        write(DAY, root=root)
    assert rows(root, db.summaries) == []
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.next_step(conn, started.run_id) == 8


def test_a_day_with_no_stories_needs_no_model(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"weak": [item("Press A")]})
    planned(root)
    result = write(DAY, root=root)

    assert (result.written, result.cost) == (0, 0.0)
    assert script_of(root, result.run_id)[1] == ("opening", None, "No story met the bar today.")


def test_it_needs_step_seven_first_and_does_not_run_twice(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"launch": STRONG})
    score(DAY, root=root)
    select(DAY, root=root, now=NOW)
    with pytest.raises(WriteError, match="Run step 7 first"):
        write(DAY, root=root, ask=writer())
    plan(DAY, root=root)
    write(DAY, root=root, ask=writer())
    fake = writer()
    assert write(DAY, root=root, ask=fake).state == "already_done"
    assert fake.requests == []


def test_a_story_with_one_stray_source_is_written_from_the_sources_that_report_it(root, monkeypatch):
    from common import selections as chosen_stories
    from common.settings import database_url

    fake_web(monkeypatch)
    grouped(root, {"startup offer": [item("Press A", title="Lab gives startups credits"), item("Press B", title="Lab opens a security programme")]})
    score(DAY, root=root, ask=rater())
    select(DAY, root=root, now=NOW)
    plan(DAY, root=root)
    fake = writer({"startup offer": dict(STORY, left_out=[2])})
    result = write(DAY, root=root, ask=fake)

    # Before, one source about another event set the whole story aside. Now it is told, without that source.
    assert (result.written, result.set_aside) == (1, 0)
    assert "left_out" in fake.requests[-2][0] and "write the story from those sources only" in fake.requests[-2][0]
    with db.connect(database_url(root)).connect() as conn:
        kept = chosen_stories.sources(conn, chosen_stories.chosen(conn, result.run_id)[0].item_ids)
    assert [row.source for row in kept] == ["Press A"]
    assert "written without Press B, which reports a different event and goes back to be grouped again" in result.report.read_text(encoding="utf-8")
    # The stray article is in no story now, so the next run groups it afresh, and it can never rejoin this one.
    in_story = {row.item_id for row in rows(root, db.story_items)}
    taken_out, = rows(root, db.splits)
    assert taken_out.item_id not in in_story and len(in_story) == 1 and taken_out.reason == "the writer found it reports a different event"


def test_a_writer_that_leaves_every_source_out_is_not_believed(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"story": [item("Press A"), item("Press B")]})
    score(DAY, root=root, ask=rater())
    select(DAY, root=root, now=NOW)
    plan(DAY, root=root)
    write(DAY, root=root, ask=writer({"story": dict(STORY, left_out=[1, 2])}))

    chosen, = rows(root, db.selections)
    assert len(chosen.item_ids) == 2


def test_when_todays_sources_are_about_something_else_the_story_keeps_what_it_had_and_they_go_back(root, monkeypatch):
    from steps.step09_check_fit.step import check_fit

    fake_web(monkeypatch)
    ids = grouped(root, {"startup offer": [item("Press A", title="Lab gives startups credits")]})
    score(DAY, root=root, ask=rater())
    select(DAY, root=root, now=NOW)
    plan(DAY, root=root)
    write(DAY, root=root, ask=writer())
    check_fit(DAY, root=root)  # told on the first day
    next_day = DAY + timedelta(days=1)
    grouped(root, {"startup offer": [item("Lab", "primary", title="Introducing the security mission")]}, day=next_day, into=ids)
    score(next_day, root=root, ask=rater())
    select(next_day, root=root, now=NOW)
    plan(next_day, root=root)
    result = write(next_day, root=root, ask=writer({"startup offer": dict(STORY, different_events=True, note="another announcement")}))

    # The update is set aside, as before. What is new: the article is not lost with it.
    assert (result.written, result.set_aside) == (0, 1)
    taken_out, = rows(root, db.splits)
    left = {row.item_id for row in rows(root, db.story_items)}
    assert taken_out.item_id not in left and len(left) == 1
