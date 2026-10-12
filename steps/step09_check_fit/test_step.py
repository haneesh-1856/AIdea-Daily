from datetime import timedelta

import pytest

from common import db, episodes, runlog
from common.settings import database_url
from steps.step05_score.step import score
from steps.step06_select.step import select
from steps.step07_plan.step import plan
from steps.step08_write.step import write
from steps.step09_check_fit.step import CheckError, check_fit
from steps.testkit import DAY, LINKING, NOW, STORY, edit_settings, fake_web, grouped, item, make_root, rater, rows, writer

SOURCES = [
    item("Lab", "primary", title="Lab ships Orion 4", summary="Orion 4 has 12 billion parameters and costs $20 a month."),
    item("Press A", title="Lab ships a thing"), item("Press B", title="Lab ships a thing"),
]
PAIR = [item("Press A", title="Lab ships a thing"), item("Press B", title="Lab ships a thing")]


@pytest.fixture
def root(tmp_path, monkeypatch):
    fake_web(monkeypatch)
    return make_root(tmp_path, monkeypatch)


@pytest.fixture
def roomy(monkeypatch):
    """Lets one story run to the full limit, as if the writer had ignored the room it was given, so that the
    episode overflows and the fitting has something to do."""
    monkeypatch.setattr(episodes, "story_room", lambda entry, settings, word_cap, stories: (settings["write"]["max_story_words"],) * 2)


def run(root, stories=None, linking=None, day=DAY):
    score(day, root=root, ask=rater())
    select(day, root=root, now=NOW)
    plan(day, root=root)
    write(day, root=root, ask=writer(stories, linking))
    return check_fit(day, root=root)


def script_of(root, run_id):
    """[(part, story title or None, text, status)] in speaking order."""
    titles = {row.id: row.title for row in rows(root, db.stories)}
    found = sorted(rows(root, db.script_lines, run_id=run_id), key=lambda row: row.position)
    return [(row.part, titles.get(row.story_id), row.text, row.status) for row in found]


def forms(root):
    """{story title: (form, reason)}"""
    titles = {row.id: row.title for row in rows(root, db.stories)}
    return {titles[row.story_id]: (row.form, row.reason) for row in rows(root, db.episode_stories)}


def long(words):
    return " ".join(["Lab shipped a thing."] * (words // 4))


def test_a_script_built_from_its_sources_passes_whole(root):
    grouped(root, {"launch": SOURCES})
    result = run(root, {"launch": dict(STORY, what_happened="Lab shipped Orion 4. It has 12 billion parameters and costs $20 a month.")})

    assert (result.state, result.status, result.removed) == ("checked", "ready", 0)
    assert script_of(root, result.run_id) == [
        ("opening", None, "Good morning.", "kept"),
        ("opening", None, "Here is the AI news.", "kept"),
        ("headline", "launch", "Lab ships a thing.", "kept"),
        ("cue", "launch", "Our top story today.", "kept"),
        ("title", "launch", "launch.", "kept"),
        ("what", "launch", "Lab shipped Orion 4.", "kept"),
        ("what", "launch", "It has 12 billion parameters and costs $20 a month.", "kept"),
        ("how", "launch", "Coverage broadly agrees.", "kept"),
        ("brief", "launch", "Lab shipped a thing.", "unused"),  # the full version is spoken, so the brief one is not
        ("closing", None, "That is all for today.", "kept"),
        # The episode ends with its sources and the thanks, made by code once it is known which stories are in it.
        ("credits", None, "Today's stories came from Lab, Press A and Press B.", "kept"),
        ("credits", None, "Links to every source are in the show notes.", "kept"),
        ("credits", None, "Thanks for listening today.", "kept"),
    ]
    assert forms(root) == {"launch": ("full", None)}
    assert result.words == 2 + 5 + 4 + 4 + 1 + 4 + 10 + 3 + 5 + 10 + 9 + 4
    # The script is final at this step, so it is written out here, before any later step runs.
    script = (root / "out" / "2026-10-06" / "script.md").read_text(encoding="utf-8")
    assert "Our top story today.\n\n### launch\n\nLab shipped Orion 4. It has 12 billion parameters and costs $20 a month." in script
    assert "61 words" in script and script.rstrip().endswith("show notes. Thanks for listening today.") and "Lab shipped a thing.\n\n## Closing" not in script
    episode, = rows(root, db.episodes)
    assert (episode.status, episode.words) == ("ready", result.words)


def test_a_sentence_with_a_number_or_name_not_in_the_sources_is_removed_not_repaired(root):
    grouped(root, {"launch": SOURCES})
    result = run(root, {"launch": dict(
        STORY,
        what_happened="Lab shipped Orion 4. It has 12 billion parameters. It costs $25 a month. Lab is in talks with Rival. It is out now.",
        how_sources_see_it="Press A calls it a bargain. The Daily Bugle disagrees.",
    )})

    removed = [(text, status) for _, _, text, status in script_of(root, result.run_id) if status == "removed"]
    assert removed == [("It costs $25 a month.", "removed"), ("Lab is in talks with Rival.", "removed"), ("The Daily Bugle disagrees.", "removed")]
    logged = [(row.text, row.reason, row.action) for row in rows(root, db.check_log)]
    assert logged == [
        ("It costs $25 a month.", "not in the sources: number 25", "removed"),
        ("Lab is in talks with Rival.", "not in the sources: name Rival", "removed"),
        ("The Daily Bugle disagrees.", "not in the sources: name Daily, name Bugle", "removed"),
        # 3 of 12 checked sentences is over a fifth, so this episode is held.
        (None, "3 of 12 checked sentences failed, more than the limit of 20%", "held"),
    ]
    assert (result.status, result.removed, forms(root)["launch"][0]) == ("held", 3, "full")


def test_too_many_failures_hold_the_episode(root):
    edit_settings(root, "hold_above = 0.2", "hold_above = 0.05")
    grouped(root, {"launch": SOURCES})
    result = run(root, {"launch": dict(STORY, what_happened="Lab shipped Orion 4. It costs $25 a month. It is out now.")})

    assert result.status == "held"
    held = rows(root, db.check_log)[-1]
    assert (held.action, held.reason) == ("held", "1 of 9 checked sentences failed, more than the limit of 5%")
    assert "HELD:" in result.report.read_text(encoding="utf-8")


def test_a_story_that_loses_its_key_facts_is_dropped(root):
    edit_settings(root, "hold_above = 0.2", "hold_above = 0.9")
    grouped(root, {"shaky": SOURCES, "solid": PAIR})
    result = run(root, {"shaky": dict(STORY, what_happened="Lab shipped Orion 5. It costs $25 a month. It is out now.")})

    assert forms(root) == {
        "shaky": ("dropped", "it lost its key facts: only 1 of 3 sentences on what happened passed the check"),
        "solid": ("full", None),
    }
    spoken = [(part, title) for part, title, _, status in script_of(root, result.run_id) if status == "kept" and title]
    assert {title for _, title in spoken} == {"solid"}


def test_each_story_in_the_episode_opens_with_a_cue_chosen_once_the_lineup_is_final(root):
    edit_settings(root, "hold_above = 0.2", "hold_above = 0.9")
    names = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh"]
    grouped(root, {name: hacker(900 - 100 * place) for place, name in enumerate(names)})
    # The second story is dropped, so it gets no cue and the third takes its place in the round.
    result = run(root, {"second": dict(STORY, different_events=True, note="A launch and a lawsuit.")})

    def cues():
        return [(title, text) for part, title, text, _ in script_of(root, result.run_id) if part == "cue"]

    assert cues() == [
        ("first", "Our top story today."), ("third", "Next up."), ("fourth", "Moving on."), ("fifth", "In other news."),
        ("sixth", "Also today."), ("seventh", "And finally."),
    ]
    # Each cue comes straight before its story's title.
    parts = [part for part, title, _, _ in script_of(root, result.run_id) if title == "third"]
    assert parts[parts.index("cue") + 1] == "title"

    # Repeating the step gives the same script, not a second set of cues.
    before = script_of(root, result.run_id)
    with db.connect(database_url(root)).begin() as conn:
        runlog.reopen(conn, result.run_id, 9)
    check_fit(DAY, root=root)
    assert script_of(root, result.run_id) == before


def test_the_brief_version_is_checked_too(root, roomy):
    edit_settings(root, "length_minutes = 15", "length_minutes = 5")
    grouped(root, {"first": SOURCES, "second": PAIR})
    result = run(root, {
        "first": dict(STORY, what_happened=long(700)),
        "second": dict(STORY, what_happened=long(400), brief="Lab shipped a thing for Rival."),
    })

    # The second story has no room in full, and its brief version failed the check, so it is left out.
    assert forms(root)["second"] == ("dropped", episodes.NO_ROOM)
    assert ("brief", "second", "Lab shipped a thing for Rival.", "removed") in script_of(root, result.run_id)


def hacker(points):
    return [item("Press A", title="Lab ships a thing"), item("Hacker News", "traction", title="Lab ships a thing", points=points)]


def test_over_the_cap_the_top_story_is_told_in_full_and_the_rest_in_brief(root, roomy):
    edit_settings(root, "length_minutes = 15", "length_minutes = 5")  # 750 words
    edit_settings(root, "hold_above = 0.2", "hold_above = 0.9")
    grouped(root, {"first": SOURCES, "second": hacker(900), "third": hacker(500), "fourth": hacker(200)})
    result = run(root, {
        "first": dict(STORY, what_happened=long(400)),
        "second": dict(STORY, what_happened=long(400)),
        "third": dict(STORY, what_happened=long(20)),  # would fit in full, but the cap was reached at the second
        "fourth": dict(STORY, what_happened=long(20)),
    })

    assert {title: form for title, (form, _) in forms(root).items()} == {
        "first": "full", "second": "brief", "third": "brief", "fourth": "brief",
    }
    assert result.words <= result.word_cap == 750
    # A story in brief form speaks its headline, intro and brief; its full text is left out, not removed.
    second = [(part, status) for part, title, _, status in script_of(root, result.run_id) if title == "second"]
    assert ("brief", "kept") in second and ("what", "unused") in second and ("what", "kept") not in second
    actions = [(row.action, row.reason) for row in rows(root, db.check_log)]
    assert actions.count(("shortened to brief", "the episode reached its word cap")) == 3


def test_a_long_story_at_the_top_does_not_push_the_others_out(root, roomy):
    edit_settings(root, "length_minutes = 15", "length_minutes = 5")
    edit_settings(root, "hold_above = 0.2", "hold_above = 0.9")
    grouped(root, {"first": SOURCES, "second": hacker(900), "third": hacker(500)})
    run(root, {name: dict(STORY, what_happened=long(600), brief=long(100)) for name in ("first", "second", "third")})

    # The first story alone would fit in full, but then the two below it could not even be told in brief.
    assert {title: form for title, (form, _) in forms(root).items()} == {"first": "brief", "second": "brief", "third": "brief"}


def test_when_even_the_brief_versions_overflow_the_lowest_ranked_are_dropped(root, roomy):
    edit_settings(root, "length_minutes = 15", "length_minutes = 5")
    edit_settings(root, "hold_above = 0.2", "hold_above = 0.9")
    names = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"]
    grouped(root, {name: hacker(900 - 100 * place) for place, name in enumerate(names)})
    result = run(root, {name: dict(STORY, brief=long(93)) for name in names})

    found = {title: form for title, (form, _) in forms(root).items()}
    assert [found[name] for name in names] == ["brief"] * 7 + ["dropped"]
    assert forms(root)["eighth"][1] == episodes.NO_ROOM and result.words <= 750


def test_a_correction_is_never_shortened_or_dropped_to_fit(root, roomy):
    ids = grouped(root, {"saga": SOURCES})
    run(root)
    next_day = DAY + timedelta(days=1)
    edit_settings(root, "length_minutes = 15", "length_minutes = 5")
    grouped(root, {
        "saga": [item("Press A", title="Correction: Lab ships a thing")],
        "big": SOURCES,
    }, day=next_day, into=ids)
    result = run(root, {"saga": dict(STORY, what_happened=long(500)), "big": dict(STORY, what_happened=long(500))}, day=next_day)

    episode, = rows(root, db.episodes, run_id=result.run_id)
    by_story = {row.story_id: row.form for row in rows(root, db.episode_stories, episode_id=episode.id)}
    # The correction keeps its 500 words; the other story, though it scores higher, is the one cut to its brief version.
    assert by_story[ids["saga"]] == "full"
    assert sorted(by_story.values()) == ["brief", "full"]


def test_no_story_runs_past_the_word_limit(root):
    edit_settings(root, "max_story_words = 600", "max_story_words = 40")
    edit_settings(root, "hold_above = 0.2", "hold_above = 0.9")
    grouped(root, {"launch": SOURCES})
    result = run(root, {"launch": dict(STORY, what_happened=long(60))})

    kept = [text for part, _, text, status in script_of(root, result.run_id) if part in ("what", "how") and status == "kept"]
    assert sum(len(text.split()) for text in kept) == 40
    assert rows(root, db.check_log)[0].reason == "past this story's limit of 40 words"


def test_a_story_cut_for_length_is_not_dropped_for_losing_its_key_facts(root):
    edit_settings(root, "max_story_words = 600", "max_story_words = 40")
    edit_settings(root, "hold_above = 0.2", "hold_above = 0.9")
    grouped(root, {"launch": SOURCES})
    run(root, {"launch": dict(STORY, what_happened=long(200))})  # the writer ran to five times its limit

    # Forty of its 50 sentences were cut for length. None of them was wrong, so the story stays.
    assert forms(root) == {"launch": ("full", None)}


def test_only_the_top_stories_get_a_headline_at_the_start(root):
    edit_settings(root, "headlines = 20", "headlines = 2")
    grouped(root, {name: hacker(900 - 100 * place) for place, name in enumerate(["first", "second", "third"])})
    result = run(root)

    headlines = [(title, status) for part, title, _, status in script_of(root, result.run_id) if part == "headline"]
    assert headlines == [("first", "kept"), ("second", "kept"), ("third", "unused")]
    # The third story is still told; it only has no headline.
    assert ("cue", "third", "And finally.", "kept") in script_of(root, result.run_id)


def test_a_story_the_writer_set_aside_is_dropped_with_the_reason(root):
    grouped(root, {"mixed": SOURCES, "solid": PAIR})
    run(root, {"mixed": dict(STORY, different_events=True, note="A launch and a lawsuit.")})

    assert forms(root) == {"mixed": ("dropped", "its sources describe different events"), "solid": ("full", None)}


def test_linking_parts_may_draw_on_any_story_and_the_date_but_nothing_else(root):
    grouped(root, {"launch": SOURCES})
    result = run(root, linking=dict(
        LINKING,
        opening="Welcome, it is Tuesday, 6 October 2026.",
        watch_list="Watch for Orion 4 pricing. Watch for the Rival launch on Friday.",
    ))

    linking = [(text, status) for part, _, text, status in script_of(root, result.run_id) if part in ("opening", "watch")]
    assert linking == [
        ("Welcome, it is Tuesday, 6 October 2026.", "kept"),
        ("Watch for Orion 4 pricing.", "kept"),
        ("Watch for the Rival launch on Friday.", "removed"),
    ]


def test_the_watch_list_does_not_mention_a_story_that_was_dropped(root, roomy):
    edit_settings(root, "length_minutes = 15", "length_minutes = 5")
    grouped(root, {
        "kept": SOURCES,
        "squeezed": [item("Press A", title="Rival opens an office in Paris"), item("Press B", title="Rival opens an office in Paris")],
    })
    rival = " ".join(["Rival opens an office in Paris."] * 70)
    result = run(root, {"kept": dict(STORY, what_happened=long(700)),
                        "squeezed": dict(STORY, headline="Rival opens an office in Paris.", what_happened=rival, brief="Nobody Corp did it.")},
                 linking=dict(LINKING, watch_list="Watch for Orion 4 pricing. Watch for the Rival office in Paris."))

    assert forms(root)["squeezed"] == ("dropped", episodes.NO_ROOM)
    watch = [(text, status) for part, _, text, status in script_of(root, result.run_id) if part == "watch"]
    assert watch == [("Watch for Orion 4 pricing.", "kept"), ("Watch for the Rival office in Paris.", "removed")]
    assert rows(root, db.check_log)[-1].reason == "it refers to a story that is not in the episode"


def test_it_needs_step_eight_first_and_does_not_run_twice(root):
    grouped(root, {"launch": SOURCES})
    score(DAY, root=root)
    select(DAY, root=root, now=NOW)
    plan(DAY, root=root)
    with pytest.raises(CheckError, match="Run step 8 first"):
        check_fit(DAY, root=root)
    write(DAY, root=root, ask=writer())
    first = check_fit(DAY, root=root)
    again = check_fit(DAY, root=root)
    assert (again.state, again.status, again.words) == ("already_done", "ready", first.words)


def test_the_first_story_that_is_only_worth_watching_is_announced():
    from types import SimpleNamespace

    from steps.step09_check_fit.step import cues_for

    def told(*segments):
        return [SimpleNamespace(story_id=place, rank=place, kind="new", segment=segment) for place, segment in enumerate(segments, 1)]

    assert cues_for(told("main", "main", "watching", "watching")) == {
        1: "Our top story today.", 2: "Next up.", 3: "Now, a few things worth watching.", 4: "And finally.",
    }
    assert cues_for(told("main", "quick_hits", "watching"))[3] == "And finally, one thing worth watching."
    # The lighter side is announced too, and the story after it takes the usual cue.
    assert cues_for(told("main", "culture", "culture", "watching")) == {
        1: "Our top story today.", 2: "And on the lighter side.", 3: "Moving on.", 4: "And finally, one thing worth watching.",
    }


def test_the_credits_name_each_outlet_once_as_it_is_said_and_end_with_the_thanks():
    from steps.step09_check_fit.step import credits_for

    assert credits_for(["The Verge AI", "Anthropic", "The Verge AI", "Hacker News"]) == [
        "Today's stories came from The Verge, Anthropic and Hacker News.",
        "Links to every source are in the show notes.",
        "Thanks for listening today.",
    ]
    assert credits_for(["Lab"])[0] == "Today's stories came from Lab."
    assert credits_for([]) == ["Thanks for listening today."]  # nothing was told, so there is nobody to credit


def test_a_dropped_story_is_not_credited(root):
    grouped(root, {"kept": SOURCES, "set aside": [item("Other Outlet")]})
    run(root, {"set aside": dict(STORY, different_events=True, note="two events")})

    credits = [text for part, _, text, status in script_of(root, 1) if part == "credits"]
    assert credits[0] == "Today's stories came from Lab, Press A and Press B."


def test_a_story_selected_but_never_told_is_not_treated_as_covered_afterwards(root):
    from datetime import timedelta

    from common import selections
    from common.settings import database_url

    # On 7 October 2026 a story was selected, set aside by the writer, and from then on held back as "already told".
    ids = grouped(root, {"told": SOURCES, "set aside": [item("Other Outlet")]})
    run(root, {"set aside": dict(STORY, different_events=True, note="two events")})

    with db.connect(database_url(root)).connect() as conn:
        covered, _ = selections.covered_before(conn, DAY + timedelta(days=1))
        recent = selections.recent_titles(conn, DAY + timedelta(days=1))
    assert covered == {ids["told"]} and recent == ["told"]
