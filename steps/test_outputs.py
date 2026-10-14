"""Steps 11 and 12, and the whole run end to end."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace

import httpx
import pytest

from common import db, episodes, model, runlog
from common.settings import database_url
from steps import runner
from steps.step02_fetch import step as fetch_step
from steps.step05_score.step import score
from steps.step06_select.step import select
from steps.step07_plan.step import plan
from steps.step08_write.step import write
from steps.step09_check_fit.step import check_fit
from steps.step11_assemble.step import SHORT_LIMIT, AssembleError, Told, assemble, host_length, short_notes_page
from steps.step12_package.step import PackageError, package
from steps.testkit import DAY, NOW, STORY, edit_settings, fake_web, grouped, item, link_of, make_root, rater, rows, writer

SOURCES = [
    item("Lab", "primary", title="Lab ships Orion 4", summary="Orion 4 has 12 billion parameters and costs $20 a month."),
    item("Press A", title="Lab ships a thing"), item("Press B", title="Lab ships a thing"),
]
PAIR = [item("Press A", title="Lab ships a thing"), item("Press B", title="Lab ships a thing")]


@pytest.fixture
def root(tmp_path, monkeypatch):
    fake_web(monkeypatch)
    return make_root(tmp_path, monkeypatch)


def checked(root, stories=None, day=DAY):
    score(day, root=root, ask=rater())
    select(day, root=root, now=NOW)
    plan(day, root=root)
    write(day, root=root, ask=writer(stories))
    return check_fit(day, root=root)


def page(result, name):
    return (result.folder / name).read_text(encoding="utf-8")


def long(words):
    return " ".join(["Lab shipped a thing."] * (words // 4))


def test_the_three_outputs_carry_the_same_checked_stories_in_the_same_order(root):
    edit_settings(root, "hold_above = 0.2", "hold_above = 0.9")
    grouped(root, {"Orion launch": SOURCES, "Second story": PAIR})
    checked(root, {"Orion launch": dict(
        STORY, headline="Lab ships Orion 4.",
        what_happened="Lab shipped Orion 4. It costs $25 a month. It has 12 billion parameters.",
        how_sources_see_it="Press A calls it a thing.",
    )})
    result = assemble(DAY, root=root)

    assert (result.state, result.stories, result.folder) == ("assembled", 2, root / "out" / "2026-10-06")
    script, newsletter, notes = (page(result, name) for name in ("script.md", "newsletter.md", "show-notes.md"))
    for text in (script, newsletter, notes):
        assert text.index("Orion launch") < text.index("Second story")
        # The sentence the check removed appears nowhere.
        assert "$25" not in text

    assert "# AI news briefing: Tuesday, 6 October 2026" in script
    assert "## Headlines\n\nLab ships Orion 4.\n\nLab ships a thing.\n" in script
    assert (
        "### Orion launch\n\nLab shipped Orion 4. It has 12 billion parameters.\n\nPress A calls it a thing.\n" in script
    )
    assert script.rstrip().endswith(
        "## Closing\n\nThat is all for today.\n\nToday's stories came from Lab, Press A and Press B. "
        "Links to every source are in the show notes. Thanks for listening today."
    )

    lab = link_of("Lab", "Orion launch")
    assert f"## Orion launch\n\n*Confirmed · new story · [Lab]({lab}), " in newsletter
    assert "Lab shipped Orion 4. It has 12 billion parameters.\n\n**How sources see it.** Press A calls it a thing." in newsletter
    assert f"## 1. Orion launch\n\nConfirmed · new story\n\n- [Lab: Lab ships Orion 4]({lab})" in notes
    assert "## 2. Second story\n\nReported · new story" in notes

    with db.connect(database_url(root)).connect() as conn:
        steps = {row.step: row.status for row in runlog.steps_of(conn, result.run_id)}
    assert (steps[10], steps[11]) == ("skipped", "done")


def test_a_story_left_out_for_length_still_appears_in_the_newsletter_and_notes_but_not_the_script(root, monkeypatch):
    monkeypatch.setattr(episodes, "story_room", lambda entry, settings, word_cap, stories: (settings["write"]["max_story_words"],) * 2)  # the writer overran
    edit_settings(root, "length_minutes = 15", "length_minutes = 5")
    grouped(root, {"Big story": SOURCES, "Squeezed story": PAIR, "Lost story": [item("Press A", title="Lab ships a thing"), item("Press C", title="Lab ships a thing")]})
    checked(root, {
        "Big story": dict(STORY, what_happened=long(700)),
        "Squeezed story": dict(STORY, what_happened=long(400), brief="Nobody Corp did it."),  # its brief fails the check
        "Lost story": dict(STORY, different_events=True, note="Two events."),
    })
    result = assemble(DAY, root=root)

    script, newsletter, notes = (page(result, name) for name in ("script.md", "newsletter.md", "show-notes.md"))
    assert "Squeezed story" not in script and "Lost story" not in script
    assert "## Also today\n\n- **Squeezed story** (Reported · new story). [Press A](" in newsletter
    assert "## Not in the episode, for length\n\n**Squeezed story** (Reported · new story)\n\n- [Press A: Lab ships a thing](" in notes
    # A story dropped because it could not be trusted is in none of them; the review sheet explains it.
    assert "Lost story" not in newsletter and "Lost story" not in notes
    review = page(package(DAY, root=root), "review.md")
    assert "- **Lost story**: its sources describe different events" in review
    assert f"- **Squeezed story**: {episodes.NO_ROOM}" in review


def told(number, label="reported", url_length=60):
    entry = SimpleNamespace(form="full", title=f"Story {number} has a fairly long title, as many do", label=label, kind="new")
    source = SimpleNamespace(source="Press A", title="A thing", url="https://press.example/" + "a" * url_length + str(number))
    return Told(entry, [source], {"headline": f"Headline of story {number}."})


CREDITS = {"credits": "Today's stories came from Lab and Press A. Links to every source are in the show notes. Thanks for listening today."}


def test_the_short_show_notes_link_the_top_stories_and_list_the_rest():
    stories = [told(number, label="rumour" if number == 7 else "reported") for number in range(1, 9)]
    text = short_notes_page(DAY, SimpleNamespace(status="ready"), stories, CREDITS, "AIdea Daily")

    assert text.startswith("AIdea Daily, Tuesday 6 October 2026.\n\nTOP STORIES\nHeadline of story 1. https://press.example/")
    assert text.count("https://") == 5 and "Headline of story 5." in text and "Headline of story 6." not in text
    assert "ALSO IN THIS EPISODE\nStory 6 has a fairly long title, as many do · Story 7 has a fairly long title, as many do (unconfirmed) · " in text
    assert text.rstrip().endswith("Today's stories came from Lab and Press A.")
    assert "#" not in text and "](" not in text  # plain text, not Markdown


def test_the_short_show_notes_stay_under_the_hosts_limit_on_a_long_day():
    stories = [told(number, url_length=150) for number in range(1, 121)]
    text = short_notes_page(DAY, SimpleNamespace(status="ready"), stories, CREDITS, "AIdea Daily")

    assert host_length(text) <= SHORT_LIMIT
    # Links went first, then titles from the end.
    assert "https://" not in text and "IN THIS EPISODE\nStory 1 has" in text and "Story 120 has" not in text and " more\n" in text
    # The host's counting, measured on 14 October 2026: a line break is 7 characters and a link far more than its address.
    assert host_length("a\nb") == 9 and host_length("https://x.example") > 2 * len("https://x.example")


def test_the_review_sheet_records_the_run_and_gives_it_its_final_status(root):
    grouped(root, {"Orion launch": SOURCES})
    checked(root, {"Orion launch": dict(STORY, headline="Lab ships Orion 4.", what_happened="Lab shipped Orion 4. It is out now.")})
    assemble(DAY, root=root)
    result = package(DAY, root=root)

    assert (result.state, result.status, result.cost) == ("packaged", "ready", 0.008)
    review = page(result, "review.md")
    assert "**Ready for your review.**" in review and "Nothing has been published or uploaded." in review
    assert "**Title:** AI news, 6 October 2026: Lab ships Orion 4" in review
    assert "**Description:** Lab ships Orion 4." in review
    assert "| 1 | Orion launch | full | confirmed | new story | 7 |" in review
    assert "## Sources used\n\nLab, Press A, Press B" in review
    assert "## Sentences the check removed (0)\n\nNone." in review
    assert "4 model requests, 4000 tokens read, 400 tokens written, $0.0080." in review
    assert "| 10 voice | skipped | Step 10 was not run, so there is no audio." in review and "| 12 package | done |" in review

    run, = rows(root, db.runs)
    assert (run.status, run.cost, run.finished_at is not None) == ("done", 0.008, True)
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.next_step(conn, run.id) is None


def test_a_held_episode_is_marked_held_everywhere(root):
    grouped(root, {"Orion launch": SOURCES})
    checked(root, {"Orion launch": dict(STORY, what_happened=(
        "Lab shipped Orion 4. It costs $25 a month. It costs $30 a year. It costs $35 a week. It is out now. "
        "It has 12 billion parameters."
    ))})
    assembled = assemble(DAY, root=root)
    result = package(DAY, root=root)

    assert result.status == "held"
    assert "> **HELD.**" in page(assembled, "script.md") and "> **HELD.**" in page(assembled, "newsletter.md")
    review = page(result, "review.md")
    assert "**HELD.** 3 of 12 checked sentences failed, more than the limit of 20%." in review
    assert '- **Orion launch**: "It costs $25 a month." (not in the sources: number 25)' in review
    # A held run is finished, not left open: a second trigger does not write it again.
    assert rows(root, db.runs)[0].status == "held"


def test_a_day_with_no_stories_still_hands_over_a_package(root):
    grouped(root, {"weak": [item("Press A")]})
    checked(root)
    assembled = assemble(DAY, root=root)
    result = package(DAY, root=root)

    assert (assembled.stories, result.status) == (0, "ready")
    assert "No story met the bar today." in page(assembled, "script.md")
    assert "No story met the bar today." in page(assembled, "newsletter.md")
    assert "**Title:** AI news, 6 October 2026\n" in page(result, "review.md")


def test_the_order_of_steps_is_enforced_and_nothing_is_built_twice(root):
    grouped(root, {"Orion launch": SOURCES})
    score(DAY, root=root)
    with pytest.raises(AssembleError, match="Run step 9 first"):
        assemble(DAY, root=root)
    with pytest.raises(PackageError, match="Run step 11 first"):
        package(DAY, root=root)
    select(DAY, root=root, now=NOW)
    plan(DAY, root=root)
    write(DAY, root=root, ask=writer())
    check_fit(DAY, root=root)
    assemble(DAY, root=root)
    package(DAY, root=root)
    assert (assemble(DAY, root=root).state, package(DAY, root=root).state) == ("already_done", "already_done")


# --- The whole run, through the one program ---

def feed(*titles):
    entries = "".join(
        f"<item><title>{title}</title><link>https://lab.example/{number}</link>"
        f"<description>{title}. It has 12 billion parameters.</description>"
        f"<pubDate>{format_datetime(datetime.now(timezone.utc) - timedelta(hours=number))}</pubDate></item>"
        for number, title in enumerate(titles, 1)
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{entries}</channel></rss>'


@pytest.fixture
def world(root, monkeypatch):
    """Every feed carries the same two articles, so both become stories that several outlets cover."""
    def get(url, params=None):
        if url == fetch_step.HN_SEARCH:
            return httpx.Response(200, json={"hits": []}, request=httpx.Request("GET", url))
        text = "<urlset></urlset>" if "sitemap" in url else feed("Lab ships Orion 4", "Lab opens an office in Paris")
        if url.endswith(("/updates", "/news")):  # a listing page, with nothing listed
            text = '<astro-island props="{&quot;articles&quot;:[1,[]]}"></astro-island>'
        return httpx.Response(200, text=text, request=httpx.Request("GET", url))

    monkeypatch.setattr(fetch_step, "get", get)
    return root


def embed(texts):
    import numpy as np
    return np.eye(len(texts))  # no two texts alike in meaning; the shared links do the grouping


def test_the_whole_day_runs_from_sources_to_package_and_a_second_run_does_nothing(world):
    said = []
    fake = writer({
        "Lab ships Orion 4": dict(STORY, headline="Lab ships Orion 4.", what_happened="Lab shipped Orion 4. It has 12 billion parameters."),
        "Lab opens an office in Paris": dict(STORY, headline="Lab opens an office in Paris.", what_happened="Lab opened an office in Paris."),
    })
    assert runner.run_day(NOW.date(), root=world, out=said.append, checks=[], ask=fake, embed=embed) is True

    folder = world / "out" / "2026-10-06"
    assert sorted(path.name for path in folder.iterdir()) == ["newsletter.md", "review.md", "scoring.md", "script.md", "show-notes-short.md", "show-notes.md"]
    script = (folder / "script.md").read_text(encoding="utf-8")
    assert "Lab shipped Orion 4. It has 12 billion parameters." in script and "Lab opened an office in Paris." in script
    assert [line.split(":")[0] for line in said[:12]] == [
        "Step 1, start", "Step 2, fetch", "Step 3, clean_store", "Step 4, group", "Step 5, score", "Step 6, select",
        "Step 7, plan", "Step 8, write", "Step 9, check_fit", "Step 10, voice", "Step 11, assemble", "Step 12, package",
    ]
    assert said[-1] == f"The package is ready for your review: {folder}"
    assert rows(world, db.runs)[0].status == "done"

    said.clear()
    requests = len(fake.requests)
    assert runner.run_day(NOW.date(), root=world, out=said.append, checks=[], ask=fake, embed=embed) is True
    assert said == ["Step 1, start: already done (run 1, attempt 1)", "The run for 2026-10-06 is finished. Use --force to run it again."]
    assert len(fake.requests) == requests


def test_a_run_without_a_model_stops_at_step_eight_and_resumes_when_one_is_given(world):
    said = []
    assert runner.run_day(NOW.date(), root=world, out=said.append, checks=[], embed=embed) is False
    assert said[-1].startswith("\nThe run stopped at step 8, write.\nNo model is chosen")
    with db.connect(database_url(world)).connect() as conn:
        steps = {row.step: (row.status, row.detail) for row in runlog.steps_of(conn, 1)}
    assert steps[7][0] == "done" and steps[8][0] == "failed" and steps[8][1].startswith("No model is chosen")

    said.clear()
    assert runner.run_day(NOW.date(), root=world, out=said.append, checks=[], ask=writer(), embed=embed) is True
    assert said[0] == "Step 1, start: resumed (run 1, attempt 1)"
    assert said[1].startswith("Step 2, fetch: 44 of 44 sources worked")  # shown again, not fetched again
    assert (world / "out" / "2026-10-06" / "script.md").exists()


def test_a_model_chosen_after_the_run_stopped_is_picked_up_without_starting_again(world, monkeypatch):
    assert runner.run_day(NOW.date(), root=world, out=lambda line: None, checks=[], embed=embed) is False
    edit_settings(world, 'provider = ""', 'provider = "anthropic"')
    edit_settings(world, '\nname = ""', '\nname = "claude-haiku-4-5"')
    fake = writer()
    monkeypatch.setattr(model, "ask", fake)
    said = []
    # With a model chosen, step 1 looks for its key and stops the run before any work if there is none.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(model.Path, "home", lambda: world)
    assert runner.run_day(NOW.date(), root=world, out=said.append, checks=[], embed=embed) is False
    assert "Model key: no key for anthropic: put ANTHROPIC_API_KEY in the .env file, or set it in the environment" in said[-1]

    said.clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key-for-the-test")
    assert runner.run_day(NOW.date(), root=world, out=said.append, checks=[], embed=embed) is True
    assert said[0] == "Step 1, start: resumed (run 1, attempt 1)"
    assert fake.requests and (world / "out" / "2026-10-06" / "script.md").exists()
    assert "| Model | claude-haiku-4-5 |" in (world / "runs" / "2026-10-06" / "08_write" / "report.md").read_text(encoding="utf-8")


def test_a_forced_second_attempt_redoes_the_day_with_the_items_already_stored(world):
    assert runner.run_day(NOW.date(), root=world, out=lambda line: None, checks=[], ask=writer(), embed=embed) is True
    said = []
    assert runner.run_day(NOW.date(), force=True, root=world, out=said.append, checks=[], ask=writer(), embed=embed) is True

    assert said[0] == "Step 1, start: new (run 2, attempt 2)"
    # 39 feeds with 2 articles each; the sitemap and listing sources and Hacker News carry none here.
    assert said[2].startswith("Step 3, clean_store: 78 raw entries, 78 kept, 0 new")
    assert said[4].startswith("Step 5, score: 2 stories scored")
    first, second = rows(world, db.runs)
    assert (first.status, second.status) == ("done", "done")
    assert len(rows(world, db.selections, run_id=second.id)) == 2


def test_the_last_steps_can_be_repeated_without_fetching_rating_or_writing_again(world):
    fake = writer()
    assert runner.run_day(NOW.date(), root=world, out=lambda line: None, checks=[], ask=fake, embed=embed) is True
    requests = len(fake.requests)
    said = []
    assert runner.run_day(NOW.date(), root=world, out=said.append, checks=[], ask=fake, embed=embed, again=9) is True

    assert said[0] == "Step 1, start: resumed (run 1, attempt 1)"
    assert said[-1].startswith("The package is ready for your review")
    assert len(fake.requests) == requests and len(rows(world, db.runs)) == 1
    assert rows(world, db.runs)[0].status == "done"
    # A step that never ran cannot be repeated from.
    assert runner.run_day(NOW.date() + timedelta(days=1), root=world, out=said.append, checks=[], again=10) is False
    assert said[-1] == "There is no run for 2026-10-07 that got as far as step 9, so there is nothing to repeat."


def test_the_run_can_stop_after_a_chosen_step(world):
    said = []
    assert runner.run_day(NOW.date(), until=5, root=world, out=said.append, checks=[], embed=embed) is True
    assert [line.split(":")[0] for line in said[:5]] == ["Step 1, start", "Step 2, fetch", "Step 3, clean_store", "Step 4, group", "Step 5, score"]
    assert "05_score" in said[-1] and not (world / "out").exists()


def test_the_script_page_lays_out_every_segment_of_the_plan():
    from steps.step07_plan.step import SEGMENTS as planned
    from steps.step11_assemble.step import SEGMENTS as shown

    # On 8 October 2026 the page had its own list, so the stories that were only worth watching were spoken
    # but missing from script.md.
    assert shown is planned and list(shown)[-1] == "watching"


def test_a_second_run_does_not_start_while_one_is_at_work(root):
    said = []
    with runner.alone(root):
        assert runner.run_day(DAY, root=root, out=said.append) is False
    assert "Another run is already working" in said[0]
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.latest_run(conn, DAY) is None
    # The lock is let go when the run ends, so the next one starts.
    with runner.alone(root):
        pass
