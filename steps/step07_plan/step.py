"""Step 7, Plan: set the order of the episode, and from each story's score how long it runs.

On a short day every story runs one length longer. Step 6 decides what is added to a short day; this step decides
how long each story is."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from common import db, episodes, runlog, selections
from common.report import step_folder, write_report
from common.settings import ROOT, database_url

STEP = 7
# The spoken order. Headlines open the episode and the watch list closes it; both are written in step 8.
SEGMENTS = {"corrections": "Corrections", "main": "Main stories", "quick_hits": "Quick hits", "culture": "On the lighter side",
            "watching": "Worth watching"}
THIN_SOURCE_WORDS = 150  # with less text than this to write from, a story can only be a quick hit


class PlanError(Exception):
    """The step could not run. The message says why."""


@dataclass
class PlanResult:
    run_id: int
    run_date: date
    state: str  # planned, already_done
    stories: int
    word_cap: int
    report: Path


def segment_of(kind: str, source_words: int, score: float = 0.0, main_from: float = 0.0, fill: str | None = None) -> str:
    """Corrections come right after the headlines. Updates are short, and so is a story with little to write from
    or one that scores under `main_from`, the score a story needs to be told at more than quick-hit length. A story
    the editor marked Watch, added to fill a short day, goes last in a segment of its own."""
    if kind == "correction":
        return "corrections"
    if fill == "watch":
        return "watching"
    if fill == "culture":
        return "culture"
    if fill == "brief":
        return "quick_hits"
    if kind == "update" or source_words < THIN_SOURCE_WORDS or score < main_from:
        return "quick_hits"
    return "main"


def words_for(choice, segment: str, source_words: int, lengths: dict, up: int) -> int:
    """How many words a story should aim for. Length follows the score, and on a short day (`up` is 1) every story
    is told one length longer. An update, a story with little to write from, and one that is only worth watching
    stay quick hits; a correction is never shorter than a short story."""
    by_score = episodes.tier_words(choice.score, lengths, up)
    if segment == "corrections":
        return max(by_score, lengths["short_words"])
    if segment == "watching" or choice.fill == "brief" or choice.kind == "update" or source_words < THIN_SOURCE_WORDS:
        return lengths["quick_words"]
    if segment == "culture":
        return lengths["short_words"]  # long enough to be enjoyed, and not lengthened on a short day
    # A story the recovery pass brought back as a full segment is never told as a quick hit.
    return max(by_score, lengths["short_words"]) if choice.fill == "recovered" else by_score


def plan(run_date: date, *, root: Path = ROOT) -> PlanResult:
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if STEP - 1 not in done:
                raise PlanError(f"No stories are selected for {run_date}. Run step 6 first.")
            if STEP in done:
                return PlanResult(run.id, run_date, "already_done", 0, episodes.get(conn, run.id).word_cap, report)
            runlog.begin_step(conn, run.id, STEP)

            # The run's frozen settings are used, not the files.
            length = run.settings["episode"]["length_minutes"]
            word_cap = length * run.settings["episode"]["words_per_minute"]
            episode_id = episodes.create(conn, run.id, length, word_cap)

            chosen = selections.chosen(conn, run.id)
            lengths = run.settings["lengths"]
            # A short day: the editor's own list makes a short episode, so every story is told one length longer.
            short = episodes.short_day([(choice.score, choice.fill) for choice in chosen], run.settings)
            placed, planned = [], {}
            for choice in chosen:
                sources = selections.sources(conn, choice.item_ids)
                words = sum(row.article_words if row.article_status == "ok" else len((row.summary or "").split()) for row in sources)
                segment = segment_of(choice.kind, words, choice.score, lengths["short_from"], choice.fill)
                planned[choice.story_id] = words_for(choice, segment, words, lengths, 1 if short else 0)
                placed.append((segment, choice, words))
            # Within a segment the ranking is kept; sorted() does not reorder equal keys.
            placed.sort(key=lambda entry: list(SEGMENTS).index(entry[0]))
            for position, (segment, choice, _) in enumerate(placed, 1):
                episodes.add_story(conn, episode_id, choice.story_id, position, segment, planned[choice.story_id])

            summary = f"{len(placed)} stories in order, word cap {word_cap}"
            runlog.finish_step(conn, run.id, STEP, detail=summary)
            room = {entry.story_id: episodes.story_room(entry, run.settings, word_cap, len(placed))[0] for entry in episodes.lineup(conn, run.id)}
    except SQLAlchemyError as exc:
        raise PlanError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    short_at = run.settings["select"].get("short_day_minutes", 0) if short else 0
    write_report(root, run_date, STEP, _report_lines(run_date, summary, placed, length, word_cap, room, short_at))
    return PlanResult(run.id, run_date, "planned", len(placed), word_cap, report)


def _report_lines(run_date: date, summary: str, placed: list, length: int, word_cap: int, room: dict, short_at: float = 0) -> list[str]:
    lines = [
        f"# Step 7, Plan: {run_date.isoformat()}",
        "",
        f"{summary}.",
        "",
        f"The episode may run up to {length} minutes, which is {word_cap} words. That is a ceiling, not a target: "
        "nothing is added to fill time.",
        "",
        f"A story's length follows its score. The stories below are given {sum(room.values())} words between them; "
        "if that and the linking parts pass the ceiling, step 9 shortens the lowest-ranked to their brief versions.",
        *(["", f"**A short day.** The editor's own list made an episode of under {short_at:g} minutes, so every story is told "
           "one length longer than its score gives. An update, a story with little source text and a story that is only "
           "worth watching stay quick hits."] if short_at else []),
        "",
        "## Running order",
        "",
        "1. **Headlines**: one line per story, written in step 8",
    ]
    number = 1
    for segment, heading in SEGMENTS.items():
        inside = [(choice, words) for placed_in, choice, words in placed if placed_in == segment]
        if not inside:
            continue
        number += 1
        lines.append(f"{number}. **{heading}**")
        lines += [
            f"    - {choice.title} ({choice.kind}, {choice.label}, score {choice.score:g}, about {room[choice.story_id]} words, "
            f"from {words} words of source text)"
            for choice, words in inside
        ]
    lines.append(f"{number + 1}. **Watch list**: written in step 8, from these stories only")
    lines.append(f"{number + 2}. **Closing**: the sources are credited and the listener is thanked, by code in step 9")
    return lines
