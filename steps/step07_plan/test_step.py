from datetime import timedelta

import pytest

from common import db
from steps.step05_score.step import score
from steps.step06_select.step import select
from steps.step07_plan.step import PlanError, plan
from common import model
from steps.testkit import (
    DAY, FILLER, MORE, NOW, FakeModel, article, edit_settings, fake_web, grouped, item, link_of, make_root, rater, ratings_for, rows,
)

STRONG = [item("Lab", "primary"), item("Press A"), item("Press B")]  # the same rating as PAIR, and more evidence, so it ranks first
PAIR = [item("Press A"), item("Press B")]


@pytest.fixture
def root(tmp_path, monkeypatch):
    return make_root(tmp_path, monkeypatch)


def run(root, day=DAY):
    score(day, root=root, ask=rater())
    select(day, root=root, now=NOW)
    return plan(day, root=root)


def outline(root, run_id):
    """[(position, segment, story title)] in speaking order."""
    titles = {row.id: row.title for row in rows(root, db.stories)}
    episode, = rows(root, db.episodes, run_id=run_id)
    found = rows(root, db.episode_stories, episode_id=episode.id)
    return [(row.position, row.segment, titles[row.story_id]) for row in sorted(found, key=lambda row: row.position)]


def pages(*names):
    """A readable article for the first source of each named story, so the story has enough text for a main slot."""
    return {link_of("Lab", name): article(FILLER, MORE) for name in names} | {
        link_of("Press A", name): article(FILLER, MORE) for name in names
    }


def test_stories_with_enough_text_are_main_stories_in_score_order(root, monkeypatch):
    fake_web(monkeypatch, pages("top", "second"))
    grouped(root, {"second": PAIR, "top": STRONG})
    result = run(root)

    assert (result.state, result.stories, result.word_cap) == ("planned", 2, 2250)
    assert outline(root, result.run_id) == [(1, "main", "top"), (2, "main", "second")]


def test_a_story_with_little_to_write_from_is_a_quick_hit_however_high_it_ranks(root, monkeypatch):
    fake_web(monkeypatch, pages("second"))
    grouped(root, {"second": PAIR, "top": STRONG})
    result = run(root)

    assert outline(root, result.run_id) == [(1, "main", "second"), (2, "quick_hits", "top")]


def test_corrections_come_first_and_updates_are_quick_hits(root, monkeypatch):
    fake_web(monkeypatch, pages("saga", "fixed", "fresh"))
    ids = grouped(root, {"saga": STRONG, "fixed": STRONG})
    run(root)
    next_day = DAY + timedelta(days=1)
    grouped(root, {
        "saga": [item("Press C"), item("Press D")],
        "fixed": [item("Press C", title="Correction: an earlier figure was wrong")],
        "fresh": STRONG,
    }, day=next_day, into=ids)
    fake_web(monkeypatch, pages("saga", "fixed") | {link_of("Lab", "fresh", next_day): article(FILLER, MORE)})
    result = run(root, next_day)

    assert outline(root, result.run_id) == [(1, "corrections", "fixed"), (2, "main", "fresh"), (3, "quick_hits", "saga")]
    text = result.report.read_text(encoding="utf-8")
    assert text.index("**Headlines**") < text.index("**Corrections**") < text.index("**Main stories**") < text.index("**Quick hits**")


@pytest.mark.parametrize("minutes, cap", [(5, 750), (30, 4500)])
def test_the_word_cap_follows_the_chosen_length(root, monkeypatch, minutes, cap):
    fake_web(monkeypatch)
    edit_settings(root, "length_minutes = 15", f"length_minutes = {minutes}")
    grouped(root, {"top": STRONG})
    assert run(root).word_cap == cap


def test_an_empty_shortlist_still_gives_an_outline(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"weak": [item("Press A")]})
    result = run(root)

    assert result.stories == 0 and outline(root, result.run_id) == []


def test_it_needs_step_six_first(root, monkeypatch):
    grouped(root, {"top": STRONG})
    score(DAY, root=root)
    with pytest.raises(PlanError, match="Run step 6 first"):
        plan(DAY, root=root)


def test_a_second_call_plans_nothing_again(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"top": STRONG})
    first = run(root)
    assert plan(DAY, root=root).state == "already_done"
    assert len(rows(root, db.episodes, run_id=first.run_id)) == 1


def test_on_a_short_day_every_story_runs_one_length_longer_and_a_watch_story_goes_last_as_a_quick_hit(root, monkeypatch):
    fake_web(monkeypatch, pages("top", "lower", "seen"))
    edit_settings(root, "short_day_minutes = 0", "short_day_minutes = 15")
    for key, value in {"long_from": 9.0, "long_words": 350, "medium_from": 8.0, "medium_words": 250, "short_from": 7.0, "short_words": 150,
                       "quick_words": 70}.items():
        edit_settings(root, f"{key} = {'0.0' if key.endswith('from') else '600'}", f"{key} = {value}")
    grouped(root, {"top": STRONG, "lower": STRONG, "seen": STRONG})
    ratings = {"top": 8, "lower": 5, "seen": {"level": 6, "action": "WATCH"}}
    # Without a recovery pass, the short-day rule itself brings in the story marked Watch.
    score(DAY, root=root, ask=FakeModel(lambda material: model.ModelError("overloaded") if material.startswith("Recovery pass")
                                        else ratings_for(material, ratings, picks=["top", "lower"])))
    select(DAY, root=root, now=NOW)
    result = plan(DAY, root=root)

    assert outline(root, result.run_id) == [(1, "main", "top"), (2, "quick_hits", "lower"), (3, "watching", "seen")]
    # Medium becomes long and a quick hit becomes short. The story that is only worth watching stays a quick hit.
    assert [row.words for row in sorted(rows(root, db.episode_stories), key=lambda row: row.position)] == [350, 150, 70]
    text = result.report.read_text(encoding="utf-8")
    assert "**A short day.** The editor's own list made an episode of under 15 minutes" in text and "**Worth watching**" in text


def test_on_a_usual_day_each_story_keeps_the_length_its_score_gives(root, monkeypatch):
    fake_web(monkeypatch, pages("top"))
    edit_settings(root, "long_words = 600", "long_words = 350")
    grouped(root, {"top": STRONG})
    result = run(root)

    assert [row.words for row in rows(root, db.episode_stories)] == [350]
    assert "A short day" not in result.report.read_text(encoding="utf-8")


def test_recovered_stories_follow_the_final_list_and_the_lighter_side_comes_in_a_segment_of_its_own(root, monkeypatch):
    fake_web(monkeypatch, pages("lead", "back in full", "back in brief", "celebrity"))
    edit_settings(root, "culture_max = 0", "culture_max = 2")
    for key, value in {"long_from": 9.0, "long_words": 350, "medium_from": 8.0, "medium_words": 250, "short_from": 7.0, "short_words": 150,
                       "quick_words": 70}.items():
        edit_settings(root, f"{key} = {'0.0' if key.endswith('from') else '600'}", f"{key} = {value}")
    grouped(root, {name: STRONG for name in ("lead", "back in full", "back in brief", "celebrity")})
    ratings = {"lead": 9, "back in full": 5, "back in brief": 8, "celebrity": {"level": 2, "action": "SKIP"}}
    score(DAY, root=root, ask=rater(ratings, picks=["lead"], recover={"back in full": "full", "back in brief": "brief"}, lighter=["celebrity"]))
    select(DAY, root=root, now=NOW)
    result = plan(DAY, root=root)

    # A story brought back in full is never told as a quick hit, whatever it scored; one brought back as a brief is.
    assert outline(root, result.run_id) == [(1, "main", "lead"), (2, "quick_hits", "back in full"), (3, "quick_hits", "back in brief"),
                                            (4, "culture", "celebrity")]
    assert [row.words for row in sorted(rows(root, db.episode_stories), key=lambda row: row.position)] == [350, 150, 70, 150]
    assert "**On the lighter side**" in result.report.read_text(encoding="utf-8")
