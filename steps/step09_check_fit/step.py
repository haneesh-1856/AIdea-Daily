"""Step 9, Check and fit: remove anything that does not match the sources, then fit the episode to its length."""

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from common import clips, db, episodes, runlog, script, selections
from common.facts import Pool, unsupported
from common.report import step_folder, write_report
from common.settings import ROOT, database_url
from common.text import word_count
from steps.formats.check import check_formats
from steps.step11_assemble.step import gather, out_folder, script_page

STEP = 9
# The parts the model wrote. A story's title and the narrator's note after it are made by code and are not checked.
CHECKED = ("opening", "headline", "what", "how", "brief", "watch", "closing")
LINKING = ("opening", "watch", "closing")
# What the narrator says before a story's title, so that a listener hears one story end and the next begin.
CUE_TOP, CUE_FIRST, CUE_LAST = "Our top story today.", "First up.", "And finally."
CUES_BETWEEN = ("Next up.", "Moving on.", "In other news.", "Also today.")
CUE_WORDS = 4  # room kept for a story's cue when the episode is fitted to its cap
# Before the first story that is only worth watching, on a short day. With one such story it is also the last.
CUE_WATCHING, CUE_ONE_TO_WATCH = "Now, a few things worth watching.", "And finally, one thing worth watching."
CUE_LIGHTER = "And on the lighter side."  # before the first celebrity, viral or curiosity story
# How the episode ends, after the closing sentence: the outlets the stories came from, then the thanks.
CREDIT, CREDIT_LINKS, THANKS = "Today's stories came from {names}.", "Links to every source are in the show notes.", "Thanks for listening today."


class CheckError(Exception):
    """The step could not run. The message says why."""


@dataclass
class CheckResult:
    run_id: int
    run_date: date
    state: str  # checked, already_done
    status: str  # ready, held
    words: int
    word_cap: int
    removed: int
    report: Path


def pool_of(entry, sources: list, earlier: list) -> Pool:
    """Everything a story's sentences may draw on: its sources in full, their outlets' names, and what was reported before."""
    texts = [entry.title]
    for row in sources:
        texts += [row.source, row.title, row.summary, row.article_text]
        if row.published_at:
            # The date a source was published is part of what it says, in whichever form the writer uses.
            when = row.published_at
            texts.append(f"{when:%Y-%m-%d} {when:%A} {when.day} {when:%B %Y}")
    for row in earlier:
        texts += [row.title, row.what_happened, row.brief]
    return Pool.of(texts)


def cues_for(told: list) -> dict[int, str]:
    """The cue for each story in the episode, given in speaking order: {story id: the cue}.

    The cues between the first story and the last come round in a fixed order, so that a day run twice reads the same.
    The first story is called the top story only when it is: a correction or an update is put first whatever its rank.
    """
    best = min((entry.rank for entry in told), default=None)
    watching = [entry.story_id for entry in told if entry.segment == "watching"]
    lighter = [entry.story_id for entry in told if entry.segment == "culture"]
    found = {}
    for place, entry in enumerate(told):
        if place and lighter and entry.story_id == lighter[0]:
            found[entry.story_id] = CUE_LIGHTER
        elif place and watching and entry.story_id == watching[0]:
            found[entry.story_id] = CUE_ONE_TO_WATCH if len(watching) == 1 else CUE_WATCHING
        elif place == 0:
            found[entry.story_id] = CUE_TOP if entry.kind == "new" and entry.rank == best else CUE_FIRST
        elif place == len(told) - 1:
            found[entry.story_id] = CUE_LAST
        else:
            found[entry.story_id] = CUES_BETWEEN[(place - 1) % len(CUES_BETWEEN)]
    return found


def spoken_source(name: str) -> str:
    """A feed's name as the narrator says it: "The Verge AI" is the outlet The Verge."""
    return name.removesuffix(" AI")


def credits_for(names: list[str]) -> list[str]:
    """The last sentences of the episode: the outlets its stories came from, in the order they were told, then the
    thanks. An episode with no stories only thanks the listener."""
    names = list(dict.fromkeys(spoken_source(name) for name in names))
    if not names:
        return [THANKS]
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return [CREDIT.format(names=listed), CREDIT_LINKS, THANKS]


def check_fit(run_date: date, *, root: Path = ROOT) -> CheckResult:
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if STEP - 1 not in done:
                raise CheckError(f"There is no draft script for {run_date}. Run step 8 first.")
            episode = episodes.get(conn, run.id)
            if STEP in done:
                return CheckResult(run.id, run_date, "already_done", episode.status, episode.words, episode.word_cap, 0, report)
            runlog.begin_step(conn, run.id, STEP)
            script.clear_log(conn, run.id)
            # A repeat of this step starts from the script as step 8 left it: the cues of the earlier try are taken
            # out, and so are clips spoken from it.
            clips.forget(conn, run.id)
            script.set_cues(conn, run.id, {})
            script.set_credits(conn, run.id, [])

            # The run's frozen settings are used, not the files.
            settings = run.settings
            lineup = episodes.lineup(conn, run.id)
            summaries = script.summaries_of(conn, run.id)
            lines = script.lines_of(conn, run.id)
            status = {line.id: "kept" for line in lines}

            pools, outlets = {}, {}
            for entry in lineup:
                sources = selections.sources(conn, entry.item_ids)
                outlets[entry.story_id] = [row.source for row in sources]
                earlier = selections.earlier_reports(conn, entry.story_id, entry.thread_id, run.run_date)
                pools[entry.story_id] = pool_of(entry, sources, earlier)
            # The linking parts may draw on any story, and on the date.
            anything = Pool.of([f"{run.run_date:%A %B %Y} {run.run_date.day}"])
            for pool in pools.values():
                anything |= pool

            # 1. Every number and name must be in the sources. A sentence that fails is removed, never repaired.
            checked = failed = 0
            for line in lines:
                if line.part not in CHECKED:
                    continue
                checked += 1
                problems = unsupported(line.text, anything if line.part in LINKING else pools[line.story_id])
                if problems:
                    failed += 1
                    status[line.id] = "removed"
                    script.log(conn, run.id, line.story_id, line.text, "not in the sources: " + ", ".join(problems), "removed")

            # 2. No story runs past the limit, and a story that lost its key facts is dropped.
            form: dict[int, str] = {}
            reason: dict[int, str] = {}
            by_story = {entry.story_id: [line for line in lines if line.story_id == entry.story_id] for entry in lineup}
            for entry in lineup:
                flag = summaries[entry.story_id].flag
                if flag:
                    form[entry.story_id] = "dropped"
                    reason[entry.story_id] = {
                        "different_events": "its sources describe different events", "nothing_new": "nothing new since it was last reported",
                        "failed": "the model failed to write it",
                    }[flag]
                    script.log(conn, run.id, entry.story_id, None, reason[entry.story_id], "dropped")
                    continue
                # Key facts are judged on the check against the sources alone: a sentence cut below for length was
                # not wrong, so it does not count against the story.
                what = [line for line in by_story[entry.story_id] if line.part == "what"]
                kept = sum(status[line.id] == "kept" for line in what)
                if kept == 0 or kept < math.ceil(len(what) / 2):
                    form[entry.story_id] = "dropped"
                    reason[entry.story_id] = f"it lost its key facts: only {kept} of {len(what)} sentences on what happened passed the check"
                    script.log(conn, run.id, entry.story_id, None, reason[entry.story_id], "dropped")
                    continue
                # Each story has its own limit, from its score.
                _, most = episodes.story_room(entry, settings, episode.word_cap, len(lineup))
                spoken = 0
                for line in by_story[entry.story_id]:
                    if line.part in ("what", "how") and status[line.id] == "kept":
                        spoken += word_count(line.text)
                        if spoken > most:
                            status[line.id] = "removed"
                            script.log(conn, run.id, entry.story_id, line.text, f"past this story's limit of {most} words", "removed")

            # 3. Fit to the cap: full versions down the ranking, then brief versions, then nothing. A story is told
            # in full only while the stories ranked below it can still be told in brief, so that a long story at the
            # top does not push the rest out. Corrections are never shortened or dropped.
            def words(story_id: int | None, parts: tuple) -> int:
                pick = by_story[story_id] if story_id else [line for line in lines if line.story_id is None]
                return sum(word_count(line.text) for line in pick if line.part in parts and status[line.id] == "kept")

            # The credits are spoken whatever is shortened, so their room is kept before any story is placed.
            still_in = [name for entry in lineup if entry.story_id not in form for name in outlets[entry.story_id]]
            used = words(None, LINKING) + sum(word_count(text) for text in credits_for(still_in))
            mode = "full"
            ranked = sorted((entry for entry in lineup if entry.story_id not in form), key=lambda entry: (entry.kind != "correction", entry.rank))
            briefs = {
                entry.story_id: CUE_WORDS + words(entry.story_id, ("headline", "title", "intro", "brief")) if words(entry.story_id, ("brief",)) else 0
                for entry in ranked
            }
            for place, entry in enumerate(ranked):
                full = CUE_WORDS + words(entry.story_id, ("headline", "title", "intro", "what", "how"))
                brief = briefs[entry.story_id]
                has_brief = brief > 0
                rest = sum(briefs[later.story_id] for later in ranked[place + 1:] if later.kind != "correction")
                if entry.kind == "correction" or (mode == "full" and used + full + rest <= episode.word_cap):
                    form[entry.story_id], used = "full", used + full
                    continue
                mode = "brief" if mode == "full" else mode
                if mode == "brief" and has_brief and used + brief <= episode.word_cap:
                    form[entry.story_id], used = "brief", used + brief
                    reason[entry.story_id] = "shortened to its brief version: the episode reached its word cap"
                    script.log(conn, run.id, entry.story_id, None, "the episode reached its word cap", "shortened to brief")
                else:
                    if mode == "brief" and has_brief:
                        mode = "nothing"
                    form[entry.story_id], reason[entry.story_id] = "dropped", episodes.NO_ROOM
                    script.log(conn, run.id, entry.story_id, None, episodes.NO_ROOM, "dropped")

            # The watch list was written before anything was dropped. A sentence of the linking parts that now refers
            # to a story not in the episode is removed.
            in_episode = Pool.of([f"{run.run_date:%A %B %Y} {run.run_date.day}"])
            for entry in lineup:
                if form[entry.story_id] != "dropped":
                    in_episode |= pools[entry.story_id]
            for line in lines:
                if line.part in LINKING and status[line.id] == "kept" and unsupported(line.text, in_episode):
                    status[line.id] = "removed"
                    script.log(conn, run.id, None, line.text, "it refers to a story that is not in the episode", "removed")

            # 4. Mark what is spoken. Lines of the version not used, and of dropped stories, are left out, not removed.
            spoken_parts = {"full": ("headline", "title", "intro", "what", "how"), "brief": ("headline", "title", "intro", "brief"), "dropped": ()}
            for line in lines:
                if line.story_id and status[line.id] == "kept" and line.part not in spoken_parts[form[line.story_id]]:
                    status[line.id] = "unused"
            # Only the top stories get a headline at the start: a long episode would otherwise open with minutes of them.
            told = sorted((entry for entry in lineup if form[entry.story_id] != "dropped"), key=lambda entry: entry.rank)
            no_headline = {entry.story_id for entry in told[settings["episode"].get("headlines", len(told)):]}
            for line in lines:
                if line.part == "headline" and line.story_id in no_headline and status[line.id] == "kept":
                    status[line.id] = "unused"
            for value in ("kept", "removed", "unused"):
                script.set_status(conn, [line_id for line_id, found in status.items() if found == value], value)
            for entry in lineup:
                episodes.set_form(conn, episode.id, entry.story_id, form[entry.story_id], reason.get(entry.story_id))
            # The cues are chosen now, when it is known which stories are in the episode and so which is first and last.
            cues = cues_for([entry for entry in lineup if form[entry.story_id] != "dropped"])
            script.set_cues(conn, run.id, cues)
            # The credits name the outlets of the stories that are in the episode, so they too are made now.
            credits = credits_for([name for entry in lineup if form[entry.story_id] != "dropped" for name in outlets[entry.story_id]])
            script.set_credits(conn, run.id, credits)

            # 5. Too many failures means the draft cannot be trusted: the episode is held for you to look at.
            share = failed / checked if checked else 0.0
            held = share > settings["check"]["hold_above"]
            if held:
                script.log(conn, run.id, None, None,
                           f"{failed} of {checked} checked sentences failed, more than the limit of {settings['check']['hold_above']:.0%}", "held")
            total = (sum(word_count(line.text) for line in lines if status[line.id] == "kept")
                     + sum(word_count(text) for text in [*cues.values(), *credits]))
            episodes.finish(conn, episode.id, total, "held" if held else "ready")

            removed = sum(found == "removed" for found in status.values())
            summary = (
                f"{'HELD' if held else 'Ready'}: {total} words of a cap of {episode.word_cap}, {removed} sentences removed, "
                f"{sum(value == 'full' for value in form.values())} stories in full, "
                f"{sum(value == 'brief' for value in form.values())} brief, {sum(value == 'dropped' for value in form.values())} dropped"
            )
            # The longer episodes are checked too, and written out.
            longer, longer_report = check_formats(conn, out_folder(root, run_date), run, lineup, pools)
            summary += "".join(f"; {one}" for one in longer)
            report_lines = _report_lines(run_date, summary, lineup, form, reason, script.log_of(conn, run.id), (failed, checked, share), run.settings)
            report_lines += longer_report
            # The script is final from here: nothing after this step changes a word of it. It is written out now,
            # so that it can be read before any audio is made from it.
            told, linking = gather(conn, run.id)
            page = script_page(run.run_date, episodes.get(conn, run.id), told, linking, settings["episode"]["words_per_minute"])
            script_file = out_folder(root, run_date) / "script.md"
            script_file.write_text("\n".join(page).rstrip() + "\n", encoding="utf-8")
            runlog.finish_step(conn, run.id, STEP, detail=summary)
    except SQLAlchemyError as exc:
        raise CheckError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    write_report(root, run_date, STEP, report_lines)
    return CheckResult(run.id, run_date, "checked", "held" if held else "ready", total, episode.word_cap, removed, report)


def _report_lines(run_date: date, summary: str, lineup: list, form: dict, reason: dict, log: list, failures: tuple, settings: dict) -> list[str]:
    failed, checked, share = failures
    lines = [
        f"# Step 9, Check and fit: {run_date.isoformat()}",
        "",
        f"{summary}.",
        "",
        "The script is final and written to `out/" + run_date.isoformat() + "/script.md`.",
        "",
        f"{failed} of {checked} checked sentences failed ({share:.0%}). Above {settings['check']['hold_above']:.0%} the episode is held.",
        "",
        "The check compares every number and name with the story's sources. It catches wrong facts; "
        "it cannot catch a wrong meaning built from the right words.",
        "",
        "| # | Story | In the episode as | Why |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| {entry.position} | {entry.title.replace('|', '/')} | {form[entry.story_id]} | {reason.get(entry.story_id, '')} |"
        for entry in lineup
    ]
    removed = [entry for entry in log if entry.action == "removed"]
    lines += ["", f"## Sentences removed ({len(removed)})", ""]
    lines += [f"- **{entry.title or 'Linking part'}**: \"{entry.text}\" ({entry.reason})" for entry in removed]
    return lines
