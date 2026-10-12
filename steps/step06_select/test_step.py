from datetime import timedelta

import httpx
import pytest

from common import db, model
from steps.step05_score.step import score
from steps.step06_select.step import SelectError, select
from steps.testkit import (
    DAY, FILLER, NOW, FakeModel, article, edit_settings, fake_web, grouped, item, link_of, make_root, rater, ratings_for, rows,
)
from steps.step01_start.step import start


@pytest.fixture
def root(tmp_path, monkeypatch):
    return make_root(tmp_path, monkeypatch)


def run(root, day=DAY):
    score(day, root=root, ask=rater())
    return select(day, root=root, now=NOW)


def selected(root, run_id):
    """{story title: selection row}"""
    titles = {row.id: row.title for row in rows(root, db.stories)}
    return {titles[row.story_id]: row for row in rows(root, db.selections, run_id=run_id)}


STRONG = [item("Lab", "primary"), item("Press A"), item("Press B")]  # rated 7 like any other; its evidence only breaks a tie
WEAK = [item("Press A")]  # a story named "weak" is rated 1


def test_every_story_at_or_above_the_minimum_is_chosen_in_rank_order(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"weak": WEAK, "strong": STRONG, "middling": [item("Press A"), item("Press B")]})
    result = run(root)

    found = selected(root, result.run_id)
    assert (result.state, result.stories) == ("selected", 2)
    assert [(title, row.rank, row.kind) for title, row in found.items()] == [("strong", 1, "new"), ("middling", 2, "new")]


def test_a_quiet_day_selects_nothing_and_is_not_padded(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"weak": WEAK})
    result = run(root)

    assert result.stories == 0
    assert "0 stories selected" in result.report.read_text(encoding="utf-8")


def test_only_the_top_stories_are_taken_and_old_news_is_left_out(root, monkeypatch):
    fake_web(monkeypatch)
    edit_settings(root, "max_stories = 8", "max_stories = 2")
    grouped(root, {name: [item("Press A"), item("Press B")] for name in ("fourth", "second", "first", "third", "rehash")})
    score(DAY, root=root, ask=rater({"first": 9, "second": 8, "third": 6, "fourth": 5, "rehash": {"level": 10, "stale": True}}))
    result = select(DAY, root=root, now=NOW)

    assert [(title, row.rank) for title, row in selected(root, result.run_id).items()] == [("first", 1), ("second", 2)]
    text = result.report.read_text(encoding="utf-8")
    assert "- rehash (10): old news: it reports something that happened more than 3 days ago" in text
    assert "- third (6): past the limit of 2 stories for one episode" in text and "- fourth (5): past the limit of 2" in text


def test_the_episode_is_the_editors_final_list_in_the_editors_order(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {name: [item("Press A"), item("Press B")] for name in ("high but passed over", "second", "first", "weak")})
    ratings = {"high but passed over": 9, "second": 8, "first": 6, "weak": 1}
    score(DAY, root=root, ask=rater(ratings, picks=["first", "second", "weak"]))
    result = select(DAY, root=root, now=NOW)

    # The editor put a lower score first and passed over the highest. Its pick under the floor of 4 is still left out.
    assert [(title, row.rank, row.score) for title, row in selected(root, result.run_id).items()] == [("first", 1, 6.0), ("second", 2, 8.0)]
    text = result.report.read_text(encoding="utf-8")
    assert "The episode is the editor's final list from step 5, in the editor's order, up to 8 stories." in text
    assert "- high but passed over (9): the editor left it out: no room" in text
    assert "- weak (1): on the editor's list, but under the floor of 4" in text


def test_without_a_final_list_the_editors_action_level_decides(root, monkeypatch):
    def answer(material):
        if material.startswith("Scored candidates"):
            return model.ModelError("overloaded")
        return ratings_for(material, {"for later": {"level": 9, "action": "WATCH"}, "for today": {"level": 6, "action": "ACT NOW"}})

    fake_web(monkeypatch)
    grouped(root, {name: [item("Press A"), item("Press B")] for name in ("for later", "for today")})
    score(DAY, root=root, ask=FakeModel(answer))
    result = select(DAY, root=root, now=NOW)

    assert list(selected(root, result.run_id)) == ["for today"]
    text = result.report.read_text(encoding="utf-8")
    assert "There is no editor's final list, so the episode is every story scoring 4 or more that the editor did not mark" in text


def test_without_ratings_the_minimum_score_cannot_apply_and_the_top_by_evidence_are_taken(root, monkeypatch):
    fake_web(monkeypatch)
    edit_settings(root, "max_stories = 8", "max_stories = 2")
    grouped(root, {"one outlet": WEAK, "three outlets": STRONG, "two outlets": [item("Press A"), item("Press B")]})
    score(DAY, root=root)  # no model: nothing is rated, and every score is far below the minimum of 4
    result = select(DAY, root=root, now=NOW)

    assert list(selected(root, result.run_id)) == ["three outlets", "two outlets"]


def test_an_older_story_needs_real_new_coverage_today_to_count_as_news(root, monkeypatch):
    fake_web(monkeypatch)
    ids = grouped(root, {"late mention": STRONG, "picked up": STRONG, "announced late": [item("Press A"), item("Press B")]})
    score(DAY, root=root, ask=rater(default=1))  # none is important enough on the first day
    assert select(DAY, root=root, now=NOW).stories == 0
    grouped(root, {"something else": [item("Press Z")]}, day=DAY + timedelta(days=1))  # a day on which none of them moved
    next_day = DAY + timedelta(days=2)
    grouped(root, {
        "late mention": [item("Blogger", "newsletter")],
        "picked up": [item("Press C"), item("Press D")],
        "announced late": [item("Lab", "primary")],
    }, day=next_day, into=ids)
    result = run(root, next_day)

    found = selected(root, result.run_id)
    by_id = {one.id: one.source for one in rows(root, db.items)}
    assert sorted(found) == ["announced late", "picked up"]
    # It was never in an episode, so it is a new story, written from all its sources, and dated to when it began.
    assert (found["picked up"].kind, str(found["picked up"].first_seen)) == ("new", "2026-10-06")
    assert [by_id[item_id] for item_id in found["picked up"].item_ids] == ["Lab", "Press A", "Press B", "Press C", "Press D"]
    assert "- late mention (7): an older story, first seen 2026-10-06, with only a late mention today" in (
        result.report.read_text(encoding="utf-8")
    )


def test_the_label_comes_from_the_kinds_of_source(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {
        "announced": STRONG,
        "written-up": [item("Press A"), item("Press B")],
        "chatter": [item("Hacker News", "traction", points=5000, comments=5000)],
    })
    found = selected(root, run(root).run_id)

    assert {title: row.label for title, row in found.items()} == {
        "announced": "confirmed", "written-up": "reported", "chatter": "rumour",
    }


def test_a_rumour_needs_high_traction(root, monkeypatch):
    fake_web(monkeypatch)
    edit_settings(root, "rumour_min_points = 300", "rumour_min_points = 6000")
    grouped(root, {"chatter": [item("Hacker News", "traction", points=5000, comments=5000)]})
    score(DAY, root=root)  # no model, so there is no rating to go by
    result = select(DAY, root=root, now=NOW)

    assert result.stories == 0
    assert "chatter (1.48): a rumour with fewer than 6000 Hacker News points" in result.report.read_text(encoding="utf-8")


def test_a_rated_story_seen_only_on_hacker_news_is_selected_on_its_score_and_told_as_unconfirmed(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"chatter": [item("Hacker News", "traction", points=40, comments=10)]})
    result = run(root)  # rated 7: far fewer than 300 points, but the score decides

    found = selected(root, result.run_id)
    assert (result.stories, found["chatter"].label) == (1, "rumour")


def test_the_ceiling_guards_a_busy_day(root, monkeypatch):
    fake_web(monkeypatch)
    edit_settings(root, "max_stories = 8", "max_stories = 1")
    grouped(root, {"strong": STRONG, "middling": [item("Press A"), item("Press B")]})
    result = run(root)

    assert list(selected(root, result.run_id)) == ["strong"]
    assert "middling (7): past the limit of 1 stories for one episode" in result.report.read_text(encoding="utf-8")


def test_sources_are_one_per_outlet_primary_first_and_capped(root, monkeypatch):
    fake_web(monkeypatch)
    edit_settings(root, "max_sources = 5", "max_sources = 3")
    grouped(root, {"big": [
        item("Hacker News", "traction", points=100),
        item("Press A"), item("Press A", title="Press A again"),
        item("Blogger", "newsletter"), item("Press B"), item("Lab", "primary"),
    ]})
    row = selected(root, run(root).run_id)["big"]

    by_id = {found.id: found.source for found in rows(root, db.items)}
    assert [by_id[item_id] for item_id in row.item_ids] == ["Lab", "Press A", "Press B"]


def test_articles_are_read_without_menus_and_adverts(root, monkeypatch):
    lab = link_of("Lab", "strong")
    fake_web(monkeypatch, {lab: article("The lab released Orion, a model with 12 billion parameters.", FILLER)})
    grouped(root, {"strong": STRONG})
    result = run(root)

    by_link = {found.id: found.url for found in rows(root, db.items)}
    read = {by_link[row.item_id]: row for row in rows(root, db.articles)}
    assert result.articles_read == 1
    assert read[lab].status == "ok" and "12 billion parameters" in read[lab].text
    assert "Advert" not in read[lab].text and "About us" not in read[lab].text
    assert read[lab].words == len(read[lab].text.split())


def test_a_site_that_refuses_is_not_forced_and_the_description_is_used(root, monkeypatch):
    lab, press_a, press_b = (link_of(source, "strong", number=n) for n, source in enumerate(["Lab", "Press A", "Press B"]))
    asked = fake_web(monkeypatch, {
        "https://lab.example/robots.txt": "User-agent: *\nDisallow: /",
        press_a: 403,
        press_b: httpx.ConnectError("no route"),
    })
    grouped(root, {"strong": STRONG})
    result = run(root)

    by_link = {found.id: found.url for found in rows(root, db.items)}
    read = {by_link[row.item_id]: row.status for row in rows(root, db.articles)}
    assert read == {lab: "refused", press_a: "refused", press_b: "failed"}
    assert lab not in asked  # robots.txt said no, so the page was never requested
    text = result.report.read_text(encoding="utf-8")
    assert "1 stories selected, 0 of 3 articles read" in text and "site refused, description used" in text


def test_a_page_with_too_little_text_counts_as_no_article(root, monkeypatch):
    fake_web(monkeypatch, {link_of("Lab", "strong"): article("Subscribe to read this story.")})
    grouped(root, {"strong": STRONG})
    run(root)

    assert {row.status for row in rows(root, db.articles)} == {"no text", "failed"}


def test_a_source_with_no_text_is_not_used_and_a_story_with_none_is_left_out(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {
        "partly readable": [item("Lab", "primary"), item("Press A", summary=None), item("Press B")],
        "unreadable": [item("Hacker News", "traction", summary=None, points=5000, comments=5000)],
    })
    result = run(root)

    found = selected(root, result.run_id)
    by_id = {one.id: one.source for one in rows(root, db.items)}
    assert list(found) == ["partly readable"]
    assert [by_id[item_id] for item_id in found["partly readable"].item_ids] == ["Lab", "Press B"]
    text = result.report.read_text(encoding="utf-8")
    assert "unreadable (7): none of its sources could be read, so there is nothing to write from" in text
    assert "- Press A (press): page could not be read, description used, 0 words. Not used as a source: no text." in text


def test_a_page_that_breaks_off_is_asked_for_once_more_but_a_refusal_is_not(root, monkeypatch):
    lab, press_a = link_of("Lab", "strong"), link_of("Press A", "strong", number=1)
    answers = {lab: [httpx.ReadTimeout("slow"), article("The lab released Orion.", FILLER)], press_a: [403, article(FILLER)]}
    asked = []

    def get(url):
        asked.append(url)
        answer = answers[url].pop(0) if answers.get(url) else 404
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer, text="") if isinstance(answer, int) else httpx.Response(200, text=answer)

    from steps.step06_select import step as select_step
    monkeypatch.setattr(select_step, "get", get)
    grouped(root, {"strong": STRONG})
    run(root)

    by_link = {found.id: found.url for found in rows(root, db.items)}
    read = {by_link[row.item_id]: row.status for row in rows(root, db.articles)}
    assert (read[lab], read[press_a]) == ("ok", "refused")
    assert (asked.count(lab), asked.count(press_a)) == (2, 1)


def test_a_covered_story_with_new_items_comes_back_as_an_update_written_from_todays_items(root, monkeypatch):
    fake_web(monkeypatch)
    ids = grouped(root, {"saga": STRONG, "one-off": STRONG})
    run(root)
    next_day = DAY + timedelta(days=1)
    grouped(root, {"saga": [item("Press C"), item("Press D")]}, day=next_day, into=ids)
    result = run(root, next_day)

    found = selected(root, result.run_id)
    by_id = {one.id: one.source for one in rows(root, db.items)}
    # The story covered yesterday with nothing new today is not selected again.
    assert list(found) == ["saga"]
    assert found["saga"].kind == "update"
    assert [by_id[item_id] for item_id in found["saga"].item_ids] == ["Press C", "Press D"]


def test_a_correction_to_a_covered_story_is_always_selected(root, monkeypatch):
    fake_web(monkeypatch)
    ids = grouped(root, {"saga": STRONG})
    run(root)
    next_day = DAY + timedelta(days=1)
    edit_settings(root, "min_score = 4.0", "min_score = 50")  # nothing scores this much
    grouped(root, {
        "saga": [item("Press A", title="Correction: the model has 12 billion parameters")],
        "other": STRONG,
    }, day=next_day, into=ids)
    result = run(root, next_day)

    found = selected(root, result.run_id)
    assert list(found) == ["saga"]
    assert found["saga"].kind == "correction" and found["saga"].score < 50


def test_a_correction_word_on_a_story_never_covered_is_ordinary_news(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"fresh": [item("Lab", "primary", title="Lab retracts its paper"), item("Press A"), item("Press B")]})
    assert selected(root, run(root).run_id)["fresh"].kind == "new"


def test_a_new_event_in_a_covered_thread_is_a_new_story(root, monkeypatch):
    fake_web(monkeypatch)
    ids = grouped(root, {"version one": STRONG})
    run(root)
    next_day = DAY + timedelta(days=1)
    grouped(root, {"version two": STRONG}, day=next_day, into=ids, threads=[("version one", "version two")])
    result = run(root, next_day)

    assert selected(root, result.run_id)["version two"].kind == "new"


def test_an_article_read_before_is_not_read_again(root, monkeypatch):
    lab = link_of("Lab", "strong")
    asked = fake_web(monkeypatch, {lab: article("The lab released Orion.", FILLER)})
    grouped(root, {"strong": STRONG})
    run(root)
    asked.clear()
    # A forced second attempt on the same day selects the story again, with the lab's article among its sources.
    start(DAY, root=root, checks=[], force=True)
    ids = {row.title: row.id for row in rows(root, db.stories)}
    grouped(root, {"strong": [item("Press C")]}, into=ids)
    second = run(root)

    assert len(selected(root, second.run_id)["strong"].item_ids) == 4
    assert lab not in asked


def test_it_needs_step_five_first(root, monkeypatch):
    fake_web(monkeypatch)
    start(DAY, root=root, checks=[])
    with pytest.raises(SelectError, match="Run step 5 first"):
        select(DAY, root=root)


def test_a_second_call_selects_nothing_again(root, monkeypatch):
    fake_web(monkeypatch)
    grouped(root, {"strong": STRONG})
    first = run(root)
    assert select(DAY, root=root).state == "already_done"
    assert len(rows(root, db.selections, run_id=first.run_id)) == 1


def test_without_a_recovery_pass_a_short_day_is_filled_from_what_the_editor_passed_over_but_never_from_a_skip(root, monkeypatch):
    fake_web(monkeypatch)
    edit_settings(root, "short_day_minutes = 0", "short_day_minutes = 15")
    edit_settings(root, "watch_from = 4.0", "watch_from = 7.0")
    names = ("picked", "known", "watched", "watched but low", "skipped")
    grouped(root, {name: [item("Press A"), item("Press B")] for name in names})
    ratings = {"picked": 9, "known": 8, "watched": {"level": 8, "action": "WATCH"}, "watched but low": {"level": 6, "action": "WATCH"},
               "skipped": {"level": 9, "action": "SKIP"}}
    # The recovery pass decides what comes back when it runs. This is the fallback for a day on which it failed.
    score(DAY, root=root, ask=FakeModel(lambda material: model.ModelError("overloaded") if material.startswith("Recovery pass")
                                        else ratings_for(material, ratings, picks=["picked"])))
    result = select(DAY, root=root, now=NOW)

    # One story of 600 words is under 15 minutes, so the day is short. The story marked Know today comes first,
    # then the one marked Watch that scores 7 or more. The lower Watch story and the Skip story stay out.
    found = selected(root, result.run_id)
    assert [(title, row.rank, row.fill) for title, row in found.items()] == [("picked", 1, None), ("known", 2, "know"), ("watched", 3, "watch")]
    text = result.report.read_text(encoding="utf-8")
    assert "The editor's list made an episode of under 15 minutes, so these were added:" in text
    assert "- known (8): the editor marked it Know today but left it off the list" in text
    assert "- watched but low (6): the editor left it out: no room" in text and "- skipped" not in text


def test_a_story_the_recovery_pass_left_out_is_not_brought_back_to_fill_a_short_day(root, monkeypatch):
    fake_web(monkeypatch)
    edit_settings(root, "short_day_minutes = 0", "short_day_minutes = 15")
    grouped(root, {name: [item("Press A"), item("Press B")] for name in ("picked", "known")})
    score(DAY, root=root, ask=rater({"picked": 9, "known": 8}, picks=["picked"]))  # the recovery pass excludes "known"
    result = select(DAY, root=root, now=NOW)

    assert list(selected(root, result.run_id)) == ["picked"]
    assert "- known (8): the editor left it out: no room" in result.report.read_text(encoding="utf-8")


def test_the_later_passes_add_stories_after_the_final_list_and_a_merged_story_lends_its_sources(root, monkeypatch):
    fake_web(monkeypatch)
    edit_settings(root, "culture_max = 0", "culture_max = 2")
    grouped(root, {
        "lead": [item("Lab", "primary")],
        "same as lead": [item("Press A"), item("Press B")],
        "worth a segment": [item("Press A")],
        "worth a line": [item("Press A")],
        "celebrity": [item("Press A")],
    })
    ratings = {"lead": 9, "same as lead": 8, "worth a segment": 6, "worth a line": 5, "celebrity": {"level": 2, "action": "SKIP"}}
    score(DAY, root=root, ask=rater(ratings, picks=["lead"], lighter=["celebrity"],
                                    recover={"same as lead": ("merge", "lead"), "worth a segment": "full", "worth a line": "brief"}))
    result = select(DAY, root=root, now=NOW)

    found = selected(root, result.run_id)
    assert [(title, row.rank, row.fill) for title, row in found.items()] == [
        ("lead", 1, None), ("worth a segment", 2, "recovered"), ("worth a line", 3, "brief"), ("celebrity", 4, "culture"),
    ]
    # The merged story is not told by itself, and its two outlets become sources of the story it joined.
    by_id = {one.id: one.source for one in rows(root, db.items)}
    assert [by_id[item_id] for item_id in found["lead"].item_ids] == ["Lab", "Press A", "Press B"]
    # The floor of 4 is for the final list: the lighter-side story was chosen on its own terms and scores 2.
    assert found["celebrity"].score == 2.0
    text = result.report.read_text(encoding="utf-8")
    assert "- worth a segment (6): brought back by the recovery pass (phase 2), as a full segment" in text
    assert "- celebrity (2): chosen for the lighter side (phase 3)" in text


def test_a_day_that_is_long_enough_is_not_filled(root, monkeypatch):
    fake_web(monkeypatch)
    edit_settings(root, "short_day_minutes = 0", "short_day_minutes = 8")
    grouped(root, {name: [item("Press A"), item("Press B")] for name in ("first", "second", "passed over")})
    score(DAY, root=root, ask=rater(picks=["first", "second"]))  # two stories of 600 words run about 9 minutes
    result = select(DAY, root=root, now=NOW)

    assert list(selected(root, result.run_id)) == ["first", "second"]


def test_a_story_first_seen_for_the_last_episode_gets_one_more_episode_on_a_single_late_mention(root, monkeypatch):
    fake_web(monkeypatch)
    ids = grouped(root, {"held back": STRONG})
    score(DAY, root=root, ask=rater(default=1))  # not important enough on its first day
    assert select(DAY, root=root, now=NOW).stories == 0
    next_day = DAY + timedelta(days=1)
    grouped(root, {"held back": [item("Blogger", "newsletter")]}, day=next_day, into=ids)
    result = run(root, next_day)

    # One mention would not carry an older story, but this one began only with the last episode. It is told as new,
    # from all its sources, and the narrator says when it first emerged.
    found = selected(root, result.run_id)
    assert (found["held back"].kind, str(found["held back"].first_seen)) == ("new", "2026-10-06")
