import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from common import db, model, runlog
from common.settings import database_url
from steps.step01_start.step import start
from steps.step05_score.step import EDITOR, ScoreError, score
from steps.testkit import DAY, QUESTIONS, FakeModel, edit_settings, grouped, item, make_root, rater, ratings_for, rows


@pytest.fixture
def root(tmp_path, monkeypatch):
    return make_root(tmp_path, monkeypatch)


def scored(root, run_date=DAY):
    """{story title: score row} for the date's run."""
    with db.connect(database_url(root)).connect() as conn:
        run = runlog.latest_run(conn, run_date)
        query = select(db.scores, db.stories.c.title).select_from(db.scores.join(db.stories))
        return {row.title: row for row in conn.execute(query.where(db.scores.c.run_id == run.id))}


COVERED = [item("Lab", "primary"), item("Press A"), item("Press B"), item("Press C"), item("Press D")]


def test_the_editors_score_decides_and_coverage_adds_nothing(root):
    grouped(root, {
        "widely covered trifle": COVERED,
        "important and barely noticed": [item("Press A")],
    })
    result = score(DAY, root=root, ask=rater({"widely covered trifle": 2, "important and barely noticed": 9}))

    found = scored(root)
    assert (result.state, result.stories, result.rated, result.chosen) == ("scored", 2, 2, 2)
    # What was counted is still recorded, but five outlets and a primary source add nothing to the score.
    assert found["widely covered trifle"].points == {
        "importance": 2.0, "outlet": 1.5, "primary": 0.5, "hn_points": 0.0, "hn_comments": 0.0, "staying": 0.0, "focus": 0.0,
    }
    assert found["widely covered trifle"].signals["outlet"] == 5
    assert (found["widely covered trifle"].total, found["important and barely noticed"].total) == (2.0, 9.0)
    text = result.report.read_text(encoding="utf-8")
    first = "| 1 | 9 | 👀 Know today | Other | #1 | important and barely noticed | rated 9 |"
    assert text.index(first) < text.index("| 2 | 2 | 👀 Know today | Other | #2 | widely covered trifle | rated 2 |")


def test_the_eight_ratings_are_averaged_by_the_weights_in_settings(root):
    answer = {"level": 0, "immediate_value": 10, "reason": "a big release"}
    grouped(root, {"story": [item("Press A")]})
    score(DAY, root=root, ask=rater({"story": answer}))
    row = scored(root)["story"]
    assert {name: row.signals["rating"][name] for name in QUESTIONS} == {**dict.fromkeys(QUESTIONS, 0), "immediate_value": 10}
    assert (row.signals["rating"]["reason"], row.signals["rating"]["action"]) == ("a big release", "KNOW TODAY")
    assert row.points["importance"] == 2.5  # the editor's weights: trying it today counts for 25 parts in 100

    edit_settings(root, "immediate_value = 25 ", "immediate_value = 75 ")  # now 75 parts in 150
    start(DAY, root=root, checks=[], force=True)
    ids = {found.title: found.id for found in rows(root, db.stories)}
    grouped(root, {"story": [item("Press B")]}, into=ids)
    score(DAY, root=root, ask=rater({"story": answer}))
    assert scored(root)["story"].points["importance"] == 5.0


def test_the_editor_gets_the_owners_instructions_and_sees_who_reported_a_story_but_not_how_popular_it_is(root):
    grouped(root, {"launch": [
        item("Lab", "primary", title="Lab ships Orion 4", summary="Orion 4 has 12 billion parameters."),
        item("Press A", title="Orion 4 arrives"),
        item("Hacker News", "traction", title="Lab ships Orion 4", points=4000, comments=900),
    ]})
    fake = rater()
    score(DAY, root=root, ask=fake)

    (rules, material), (final_rules, final) = fake.requests
    assert rules == final_rules == EDITOR.read_text(encoding="utf-8") and "Managing Editorial Editor" in rules
    assert material.startswith("Stories to rate. Date: Tuesday, 6 October 2026\n\n") and "more than 3 days before" in material
    assert "\n\n1. launch\n   Also reported as: Lab ships Orion 4 / Orion 4 arrives\n" in material
    assert "   Sources: Lab (primary), Press A (press), Hacker News (discussion)\n   Orion 4 has 12 billion parameters." in material
    assert "4000" not in material and "900" not in material
    # There is no episode before this one, and the story was collected for this one.
    assert "This is the first episode, so it covers the last few days." in material
    assert "   Collected: new since the last episode\n   Sources: Lab (primary)" in material
    assert final.startswith("Scored candidates. Date: Tuesday, 6 October 2026\n\n")
    assert final.endswith("1. launch\n   Weighted score: 7.00 | Action: KNOW TODAY | Category: Other | New since the last episode: yes\n   rated 7")
    assert [(call.step, call.purpose, call.cost) for call in rows(root, db.model_calls)] == [(5, "rate", 0.002), (5, "edit", 0.002)]


def test_the_final_list_is_the_editors_and_the_report_shows_it(root):
    grouped(root, {name: [item("Press A")] for name in ("alpha", "beta", "gamma")})
    result = score(DAY, root=root, ask=rater({"alpha": 9, "beta": 6, "gamma": 8}, picks=["beta", "alpha"]))

    found = scored(root)
    assert result.chosen == 2
    # The editor put the lower-scored story first. The scores stand; the place on the list is kept beside them.
    assert {title: (row.total, (row.signals["rating"].get("final") or {}).get("rank")) for title, row in found.items()} == {
        "alpha": (9.0, 2), "beta": (6.0, 1), "gamma": (8.0, None),
    }
    assert found["gamma"].signals["rating"]["near_miss"] == "no room"
    text = result.report.read_text(encoding="utf-8")
    assert "3 stories scored, 3 rated by the editor, 2 on the final list." in text
    assert text.index("### #1 — beta, in short") < text.index("### #2 — alpha, in short") < text.index("## Not selected")
    assert "👀 Know today · Other · score 6\n\n- **What happened:** beta happened.\n- **Why it matters:** It matters." in text
    assert "- **gamma** (8): no room" in text
    assert "| 2 | 8 | 👀 Know today | Other |  | gamma | rated 8 |" in text and "| 3 | 6 | 👀 Know today | Other | #1 | beta | rated 6 |" in text


def test_a_story_the_editor_marks_skip_is_not_put_forward_for_the_final_list(root):
    grouped(root, {"worth telling": [item("Press A")], "event notice": [item("Press A")]})
    fake = rater({"event notice": {"level": 6, "action": "SKIP"}})
    result = score(DAY, root=root, ask=fake)

    final = next(material for _, material in fake.requests if material.startswith("Scored candidates"))
    assert "worth telling" in final and "event notice" not in final
    # The recovery pass, though, looks at everything left out, a skipped story included.
    assert "event notice" in fake.requests[-1][1] and fake.requests[-1][1].startswith("Recovery pass")
    assert result.chosen == 1 and "| ❌ Skip | Other |  | event notice |" in result.report.read_text(encoding="utf-8")


def test_the_editor_is_told_what_the_last_episodes_covered(root, monkeypatch):
    from steps.step06_select.step import select
    from steps.testkit import NOW, fake_web

    fake_web(monkeypatch)
    grouped(root, {"told yesterday": [item("Press A")]})
    score(DAY, root=root, ask=rater())
    select(DAY, root=root, now=NOW)
    next_day = DAY + timedelta(days=1)
    grouped(root, {"new today": [item("Press B")]}, day=next_day)
    fake = rater()
    score(next_day, root=root, ask=fake)

    final = fake.requests[-1][1]
    assert "Select one of these again only when today's candidate adds something materially new:\n- told yesterday\n\n1. new today" in final


def test_when_the_final_list_cannot_be_made_the_scores_stand_and_the_report_says_so(root):
    def answer(material):
        return model.ModelError("overloaded") if material.startswith("Scored candidates") else ratings_for(material)

    grouped(root, {"story": [item("Press A")]})
    result = score(DAY, root=root, ask=FakeModel(answer))

    assert (result.rated, result.chosen, scored(root)["story"].total) == (1, 0, 7.0)
    text = result.report.read_text(encoding="utf-8")
    assert "- The final list could not be made: overloaded Step 6 takes the stories marked Act now or Know today instead" in text
    assert "## Top AI news today" not in text


def test_ratings_are_clamped_and_a_story_the_model_skips_is_left_unrated(root):
    def answer(material):
        if material.startswith("Scored candidates"):
            return ratings_for(material)
        given = {"action": "KNOW TODAY", "category": "Other", "new_today": True}
        return {"ratings": [
            {"story": 1, "headline": "first", **dict.fromkeys(QUESTIONS, 5), "immediate_value": 99, "ai_impact": -4, "stale": True, "reason": "x", **given},
            {"story": 7, "headline": "no such story", **dict.fromkeys(QUESTIONS, 9), "stale": False, "reason": "no such story", **given},
        ]}

    grouped(root, {"first": [item("Press A")], "second": [item("Press A")]})
    result = score(DAY, root=root, ask=FakeModel(answer))

    found = scored(root)
    rating = found["first"].signals["rating"]
    assert (rating["immediate_value"], rating["ai_impact"], rating["magnitude"], rating["stale"]) == (10, 0, 5, True)
    assert found["second"].signals["rating"] is None and found["second"].points["importance"] == 0.0
    text = result.report.read_text(encoding="utf-8")
    assert result.rated == 1 and "- 1 stories could not be matched to a rating in the model's answer and are not rated" in text
    assert "| 👀 Know today (old news) |" in text and "| not rated |" in text


def test_a_rating_goes_to_the_story_whose_headline_it_names_even_when_the_numbering_slips(root):
    def answer(material):
        if material.startswith("Scored candidates"):
            return ratings_for(material)
        # The model numbers its answers one too high from the second story on, as happened on 7 October 2026.
        found = ratings_for(material, {"alpha": 9, "beta": 2, "gamma": 5})["ratings"]
        for rating in found[1:]:
            rating["story"] += 1
        return {"ratings": found}

    grouped(root, {"alpha": [item("Press A")], "beta": [item("Press A")], "gamma": [item("Press A")]})
    result = score(DAY, root=root, ask=FakeModel(answer))

    found = scored(root)
    assert result.rated == 3
    assert {title: row.signals["rating"]["reason"] for title, row in found.items()} == {
        "alpha": "rated 9", "beta": "rated 2", "gamma": "rated 5",
    }


def test_many_stories_are_rated_in_batches_and_a_failed_batch_leaves_the_rest_rated(root):
    calls = []

    def answer(material):
        calls.append(material)
        return model.ModelError("overloaded") if len(calls) == 2 else ratings_for(material)

    grouped(root, {f"story {number}": [item("Press A")] for number in range(60)})
    result = score(DAY, root=root, ask=FakeModel(answer))

    # Four requests of 15 stories, then one for the final list, which is shown the 45 that were rated.
    assert [len(re.findall(r"^\d+\. ", material, flags=re.MULTILINE)) for material in calls] == [15, 15, 15, 15, 45]
    assert (result.stories, result.rated, result.chosen) == (60, 45, 45)
    assert "- 15 stories were not rated: overloaded" in result.report.read_text(encoding="utf-8")


def test_without_a_model_stories_are_ranked_on_evidence_alone_and_the_report_says_so(root):
    grouped(root, {
        "viral": [item("Hacker News", "traction", points=999, comments=99)],
        "covered": [item("Lab", "primary"), item("Press A"), item("Press A", title="Press A again"), item("Press B")],
    })
    result = score(DAY, root=root)

    found = scored(root)
    assert result.rated == 0 and rows(root, db.model_calls) == []
    # Press A wrote twice and counts once; Hacker News is not an outlet.
    assert found["covered"].signals == {
        "rating": None, "first_seen": "2026-10-06", "late": False,
        "outlet": 3, "primary": 1, "hn_points": 0, "hn_comments": 0, "staying": 0, "focus": 0,
    }
    assert (found["covered"].total, found["viral"].points["hn_points"], found["viral"].points["hn_comments"]) == (2.0, 0.9, 0.2)
    assert "**No story was rated, because no model is chosen.**" in result.report.read_text(encoding="utf-8")


def test_coverage_on_a_later_day_is_recorded_as_staying_power(root):
    ids = grouped(root, {"saga": [item("Lab", "primary")], "one-off": [item("Press A")]})
    score(DAY, root=root, ask=rater())
    next_day = DAY + timedelta(days=1)
    grouped(root, {"saga": [item("Press B")]}, day=next_day, into=ids)
    result = score(next_day, root=root, ask=rater())

    found = scored(root, next_day)
    # Only the story that gained an item is scored again; the first day's score is untouched.
    assert result.stories == 1 and list(found) == ["saga"]
    # It is recorded with the rest of the evidence. A rated story's score is the editor's alone.
    assert (found["saga"].signals["staying"], found["saga"].points["staying"], found["saga"].total) == (1, 0.3, 7.0)
    assert scored(root, DAY)["saga"].total == 7.0


def test_an_older_story_never_in_an_episode_is_scored_on_todays_evidence_only(root, monkeypatch):
    from steps.step06_select.step import select
    from steps.testkit import NOW, fake_web

    fake_web(monkeypatch)
    big = [item("Lab", "primary"), item("Press A"), item("Press B"), item("Hacker News", "traction", points=900, comments=90)]
    ids = grouped(root, {"sleeper": big, "covered": big})
    score(DAY, root=root, ask=rater({"sleeper": 0}))  # too minor to be selected on the first day
    select(DAY, root=root, now=NOW)
    next_day = DAY + timedelta(days=1)
    grouped(root, {"sleeper": [item("Press C")], "covered": [item("Press C")]}, day=next_day, into=ids)
    result = score(next_day, root=root, ask=rater())

    found = scored(root, next_day)
    # The first day's three outlets, primary source and Hacker News thread no longer count for the sleeper.
    assert found["sleeper"].signals["late"] is True and found["sleeper"].signals["first_seen"] == "2026-10-06"
    assert (found["sleeper"].signals["outlet"], found["sleeper"].signals["primary"], found["sleeper"].signals["hn_points"]) == (1, 0, 0)
    # A story already in an episode keeps its whole history: it can only come back as an update.
    assert found["covered"].signals["late"] is False and found["covered"].signals["outlet"] == 4
    assert "(first seen 2026-10-06; only today's coverage is counted)" in result.report.read_text(encoding="utf-8")


def test_a_focus_area_adds_its_points_once(root):
    edit_settings(root, "focus = []", 'focus = ["open-weight", "robotics"]')
    grouped(root, {
        "matching": [item("Press A", title="An open-weight model for robotics labs")],
        "other": [item("Press A", title="A closed model")],
    })
    score(DAY, root=root)

    found = scored(root)
    assert (found["matching"].signals["focus"], found["matching"].points["focus"]) == (1, 1.0)
    assert found["other"].signals["focus"] == 0


def test_a_story_gets_the_topic_whose_words_appear_most(root):
    grouped(root, {
        "funding": [item("Press A", title="Startup raises new funding", summary="The valuation doubles.")],
        "gadget": [item("Press A", title="A quiet week")],
    })
    result = score(DAY, root=root)

    found = scored(root)
    assert (found["funding"].topic, found["gadget"].topic) == ("business", None)
    assert "| business | 1 |" in result.report.read_text(encoding="utf-8")


def test_it_needs_step_four_first(root):
    start(DAY, root=root, checks=[])
    with pytest.raises(ScoreError, match="Run step 4 first"):
        score(DAY, root=root)


def test_a_second_call_scores_nothing_again(root):
    grouped(root, {"story": [item("Press A")]})
    score(DAY, root=root, ask=rater())
    fake = rater()
    assert score(DAY, root=root, ask=fake).state == "already_done"
    assert len(scored(root)) == 1 and fake.requests == []


def test_the_editor_is_told_the_window_the_episode_covers_and_where_each_story_stands_in_it(root, monkeypatch):
    from steps.step06_select.step import select
    from steps.testkit import NOW, fake_web

    fake_web(monkeypatch)
    ids = grouped(root, {"told before": [item("Press A")], "held back": [item("Press A")]})
    score(DAY, root=root, ask=rater(picks=["told before"]))
    select(DAY, root=root, now=NOW)
    next_day = DAY + timedelta(days=1)
    grouped(root, {"told before": [item("Press B")], "held back": [item("Press B")], "fresh": [item("Press B")]}, day=next_day, into=ids)
    fake = rater()
    score(next_day, root=root, ask=fake)

    material = fake.requests[0][1]
    # "Today" is the time since the last run, so a morning run does not find yesterday evening's news old.
    assert "This episode covers everything collected since the last episode, which was made on " in material
    assert '"Today" in your instructions means this window, not the calendar date' in material
    also = "\n   Also reported as: Lab ships a thing\n   Collected: "
    assert f"told before{also}first seen 2026-10-06, already told in an episode, with new coverage since the last episode" in material
    assert f"held back{also}first seen 2026-10-06, not yet told in an episode, with new coverage since the last episode" in material
    assert f"fresh{also}new since the last episode" in material


def test_hacker_news_adds_to_a_rated_story_and_a_story_without_a_thread_loses_nothing(root):
    edit_settings(root, "traction_max = 0.0", "traction_max = 1.5")
    grouped(root, {
        "no thread": [item("Press A")],
        "popular": [item("Press A"), item("Hacker News", "traction", points=300, comments=80)],
        "huge thread": [item("Press A"), item("Hacker News", "traction", points=90000, comments=9000)],
        "liked a bit": [item("Press A"), item("Hacker News", "traction", points=50, comments=5)],
    })
    result = score(DAY, root=root, ask=rater({"no thread": 8, "popular": 7, "huge thread": 7, "liked a bit": 7}))

    found = scored(root)
    # Points and comments count at their usual weights: 300 points and 80 comments add 0.93, and 50 and 5 add 0.59.
    # No thread, however large, adds more than the most allowed. A story with no thread keeps the editor's score.
    assert {title: row.total for title, row in found.items()} == {"no thread": 8.0, "popular": 7.93, "huge thread": 8.5, "liked a bit": 7.59}
    text = result.report.read_text(encoding="utf-8")
    assert "Hacker News points and comments add to it, at most 1.5. A story with no Hacker News thread loses nothing." in text
    assert "| 7 | 300 | 0.93 |" in text


def test_after_the_final_list_the_editor_looks_again_at_everything_left_out_and_then_for_the_lighter_side(root):
    edit_settings(root, "culture_max = 0", "culture_max = 2")
    names = ("lead", "second", "worth a segment", "worth a line", "same as lead", "really out", "celebrity", "meme")
    grouped(root, {name: [item("Press A")] for name in names})
    ratings = {"lead": 9, "second": 8, "worth a segment": 6, "worth a line": 5, "same as lead": 7, "really out": 4,
               "celebrity": {"level": 2, "action": "SKIP"}, "meme": {"level": 1, "action": "SKIP"}}
    fake = rater(ratings, picks=["second", "lead"],
                 recover={"worth a segment": "full", "worth a line": "brief", "same as lead": ("merge", "lead")},
                 lighter=["celebrity"])
    result = score(DAY, root=root, ask=fake)

    found = scored(root)
    lineup = {title: row.signals["rating"].get("lineup") for title, row in found.items()}
    # Phase 1 keeps the editor's own order. Phase 2's stories follow it, full segments before briefs, and phase 3's come last.
    assert {title: (entry["rank"], entry["phase"], entry["as"]) for title, entry in lineup.items() if entry} == {
        "second": (1, 1, "full"), "lead": (2, 1, "full"), "worth a segment": (3, 2, "recovered"), "worth a line": (4, 2, "brief"),
        "celebrity": (5, 3, "culture"),
    }
    assert result.chosen == 5
    # Every story left out has a decision and its reason; a merge names the story it joins.
    assert found["same as lead"].signals["rating"]["recovery"] == {"decision": "merge", "reason": "worth merge", "into": found["lead"].story_id}
    assert found["really out"].signals["rating"]["recovery"]["decision"] == "exclude" and found["really out"].signals["rating"]["near_miss"] == "no room"
    # The two later passes are sent the main instructions with their own section added, in that order.
    kinds = [material.split(".")[0] for _, material in fake.requests]
    assert kinds == ["Stories to rate", "Scored candidates", "Recovery pass", "Lighter side pass"]
    assert "Preventing Valuable News from Being Lost" in fake.requests[2][0] and "Managing Editorial Editor" in fake.requests[2][0]
    assert "Celebrity Trends, Viral AI Stories, and Curiosity" in fake.requests[3][0] and "at most 2" in fake.requests[3][1]
    # The lighter-side pass is not shown what the recovery pass already brought back or merged.
    assert "worth a segment" not in fake.requests[3][1].split("Remaining:")[1] and "same as lead" not in fake.requests[3][1].split("Remaining:")[1]
    assert [call.purpose for call in rows(root, db.model_calls)] == ["rate", "edit", "recover", "culture"]
    text = result.report.read_text(encoding="utf-8")
    assert "8 stories scored, 8 rated by the editor, 2 on the final list, 2 recovered, 1 merged, 1 for the lighter side." in text
    assert "| Full segment | 6 | worth a segment | worth full |" in text and '| Merged into "lead" | 7 | same as lead | worth merge |' in text
    assert "## Phase 3: the lighter side" in text and "| 8 | 2 | celebrity | people will talk about it |" in text
    assert "| #3 (recovered) | worth a segment |" in text and "| #5 (lighter side) | celebrity |" in text and "| merged | same as lead |" in text


def test_when_a_later_pass_fails_the_final_list_stands_and_the_report_says_so(root):
    def answer(material):
        return model.ModelError("overloaded") if material.startswith("Recovery pass") else ratings_for(material, picks=["kept"])

    grouped(root, {"kept": [item("Press A")], "left out": [item("Press A")]})
    result = score(DAY, root=root, ask=FakeModel(answer))

    assert result.chosen == 1 and scored(root)["kept"].signals["rating"]["lineup"] == {"rank": 1, "phase": 1, "as": "full"}
    assert "- The recovery pass (phase 2) could not be made: overloaded The episode keeps to the final list." in result.report.read_text(encoding="utf-8")


def test_a_story_with_nothing_to_judge_by_is_rated_from_the_opening_of_its_article(root, monkeypatch):
    from steps.step06_select.step import select
    from steps.testkit import NOW, fake_web, link_of

    grouped(root, {
        "Why is nobody talking about Vega 4.1 Flash?": [item("Hacker News", "traction", title="Why is nobody talking about Vega 4.1 Flash?", summary=None)],
        "described": [item("Press A", summary="Lab ships a thing that does many useful things for the people who build with it every day.")],
        "unreadable": [item("Hacker News", "traction", title="unreadable", summary=None)],
    })
    opening = "Vega Labs released Vega 4.1 Flash today, a small model with open weights. " * 30
    asked = []

    def read(url):
        asked.append(url)
        if "unreadable" in url:
            raise RuntimeError("the page broke")
        return "ok", opening

    fake = rater()
    result = score(DAY, root=root, ask=fake, read=read)

    material = fake.requests[0][1]
    # Only the stories with too little description are read, and the editor sees the first 150 words.
    assert sorted(asked) == sorted(link_of("Hacker News", name) for name in ("Why is nobody talking about Vega 4.1 Flash?", "unreadable"))
    shown = " ".join(opening.split()[:150])
    assert f"   (no description available)\n   Opening of the article: {shown}\n\n" in material
    assert material.count("Opening of the article:") == 1
    # A page that cannot be read does not stop the scoring: that story is rated from its headline, as before.
    assert result.rated == 3 and "3. unreadable\n" in material
    assert "1 story had no description to judge by, so the editor was shown the opening of the article instead (2 pages read now)." in (
        result.report.read_text(encoding="utf-8"))
    # What was read is kept: step 6 does not ask for the page again, and a second scoring would not either.
    stored = {row.item_id: row.status for row in rows(root, db.articles)}
    assert sorted(stored.values()) == ["failed", "ok"]
    web = fake_web(monkeypatch)
    select(DAY, root=root, now=NOW)
    assert link_of("Hacker News", "Why is nobody talking about Vega 4.1 Flash?") not in web


def test_a_returning_story_shows_the_editor_what_was_reported_since_the_last_episode(root):
    ids = grouped(root, {"Lab ships Orion": [
        item("Press A", title="Lab ships Orion", summary="Orion is a new model from Lab, and it is available to everyone from today at no cost at all."),
        item("Press B", title="Orion arrives"), item("Press C", title="Hands on with Orion"),
    ]})
    score(DAY, root=root, ask=rater())
    next_day = DAY + timedelta(days=1)
    grouped(root, {"Lab ships Orion": [item("Press D", title="Lab cuts Orion prices by 70%", summary="Lab cut the price of Orion by 70%.")],
                   "fresh": [item("Press D")]}, day=next_day, into=ids)
    fake = rater()
    score(next_day, root=root, ask=fake)

    material = fake.requests[0][1]
    # The story's own title stays first, since a rating is matched to its story by it; the oldest headlines follow.
    assert "\n\n1. Lab ships Orion\n   Also reported as: Orion arrives / Hands on with Orion\n" in material
    # Today's item is named with its own description, set apart from the story's longest one, which is an old one.
    assert ("   Reported since the last episode: Lab cuts Orion prices by 70% (Press D)\n"
            "   Described since the last episode as: Lab cut the price of Orion by 70%.\n"
            "   Sources: Press A (press), Press B (press), Press C (press), Press D (press)\n"
            "   Orion is a new model from Lab, and it is available to everyone") in material
    # A story that is all new has nothing to set apart.
    assert material.count("Reported since the last episode:") == 1
