"""Step 11, Assemble: build the newsletter and the show notes from the same checked content as the script.

The script itself is written by step 9, the moment it is final. The functions that lay it out are here because
all three pages are built from the same gathered content."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

import numpy
import soundfile

from common import clips, db, episodes, formats, runlog, script, selections
from common.report import step_folder, write_report
from common.settings import ROOT, database_url
from steps.step07_plan.step import SEGMENTS  # the script page lays out the plan's segments, in the plan's order

STEP = 11
VOICE_STEP = 10
KINDS = {"new": "new story", "update": "update", "correction": "correction"}
NOTHING_TODAY = "No story met the bar today."


class AssembleError(Exception):
    """The step could not run. The message says why."""


@dataclass
class AssembleResult:
    run_id: int
    run_date: date
    state: str  # assembled, already_done
    folder: Path
    stories: int
    report: Path


def out_folder(root: Path, run_date: date) -> Path:
    folder = root / "out" / run_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def long_date(day: date) -> str:
    return f"{day.day} {day:%B %Y}"


@dataclass
class Told:
    """One story as the outputs carry it: only sentences that passed the check, and its sources."""

    entry: object  # its place in the outline, with form, label, kind and title
    sources: list
    text: dict  # part -> the sentences of that part, joined

    @property
    def links(self) -> str:
        return ", ".join(f"[{row.source}]({row.url})" for row in self.sources)

    @property
    def tag(self) -> str:
        return f"{self.entry.label.capitalize()} · {KINDS[self.entry.kind]}"


def gather(conn, run_id: int) -> tuple[list[Told], dict]:
    """The run's stories in outline order, and the linking parts. Sentences the check removed are never included."""
    lines = script.lines_of(conn, run_id)
    linking = {part: " ".join(line.text for line in lines if line.part == part and line.status == "kept")
               for part in ("opening", "watch", "closing", "credits")}
    told = []
    for entry in episodes.lineup(conn, run_id):
        mine = [line for line in lines if line.story_id == entry.story_id]
        # A story left out for length keeps its checked brief version for the newsletter: those lines are
        # "unused", not "removed".
        wanted = ("kept",) if entry.form in ("full", "brief") else ("unused",)
        text = {part: " ".join(line.text for line in mine if line.part == part and line.status in wanted)
                for part in ("headline", "cue", "intro", "what", "how", "brief")}
        told.append(Told(entry, selections.sources(conn, entry.item_ids), text))
    return told, linking


def script_page(day: date, episode, told: list[Told], linking: dict, pace: int) -> list[str]:
    spoken = [story for story in told if story.entry.form in ("full", "brief")]
    lines = [
        f"# AI news briefing: {day:%A}, {long_date(day)}",
        "",
        f"*{episode.words} words, about {max(1, round(episode.words / pace))} minutes at {pace} words a minute. "
        f"The cap was {episode.word_cap} words.*",
        "",
    ]
    if episode.status == "held":
        lines += ["> **HELD.** Too many sentences failed the check against the sources. Read `review.md` before using this script.", ""]
    lines += ["## Opening", "", linking["opening"], ""]
    if spoken:
        lines += ["## Headlines", ""]
        lines += [story.text["headline"] + "\n" for story in spoken if story.text["headline"]]
    for segment, heading in SEGMENTS.items():
        inside = [story for story in spoken if story.entry.segment == segment]
        if not inside:
            continue
        lines += [f"## {heading}", ""]
        for story in inside:
            parts = ("intro", "what", "how") if story.entry.form == "full" else ("intro", "brief")
            # The cue is spoken before the title, so it is shown before it.
            lines += [story.text["cue"], ""] if story.text["cue"] else []
            lines += [f"### {story.entry.title}", ""]
            lines += [story.text[part] + "\n" for part in parts if story.text[part]]
    if linking["watch"]:
        lines += ["## Watch list", "", linking["watch"], ""]
    lines += ["## Closing", "", linking["closing"]]
    # The credits and the thanks are spoken last. They are for the ear: the newsletter and show notes link each source.
    lines += ["", linking["credits"]] if linking.get("credits") else []
    return lines


def newsletter_page(day: date, episode, told: list[Told]) -> list[str]:
    shown = [story for story in told if story.entry.form in ("full", "brief")]
    also = [story for story in told if story.entry.form == "dropped" and story.entry.reason == episodes.NO_ROOM]
    lines = [f"# AI news: {long_date(day)}", ""]
    if episode.status == "held":
        lines += ["> **HELD.** Too many sentences failed the check against the sources. Read `review.md` before sending this.", ""]
    if not shown and not also:
        lines += [NOTHING_TODAY]
    for story in shown:
        lines += [f"## {story.entry.title}", "", f"*{story.tag} · {story.links}*", ""]
        if story.entry.form == "full":
            lines += [story.text["what"], ""]
            if story.text["how"]:
                lines += [f"**How sources see it.** {story.text['how']}", ""]
        else:
            lines += [story.text["brief"], ""]
    if also:
        lines += ["## Also today", ""]
        lines += [f"- **{story.entry.title}** ({story.tag}). {story.text['brief']} {story.links}".replace("  ", " ") for story in also]
    return lines


def notes_page(day: date, told: list[Told]) -> list[str]:
    shown = [story for story in told if story.entry.form in ("full", "brief")]
    also = [story for story in told if story.entry.form == "dropped" and story.entry.reason == episodes.NO_ROOM]
    lines = [f"# Show notes: {long_date(day)}", ""]
    if not shown and not also:
        lines += [NOTHING_TODAY]
    for number, story in enumerate(shown, 1):
        lines += [f"## {number}. {story.entry.title}", "", story.tag, ""]
        lines += [f"- [{row.source}: {row.title}]({row.url})" for row in story.sources]
        lines.append("")
    if also:
        lines += ["## Not in the episode, for length", ""]
        for story in also:
            lines += [f"**{story.entry.title}** ({story.tag})", ""]
            lines += [f"- [{row.source}: {row.title}]({row.url})" for row in story.sources]
            lines.append("")
    return lines


def join_clips(found: list, target: Path) -> float:
    """Join the spoken clips in order, with the pause each one asks for, into one MP3. Returns its length in seconds."""
    pieces, rate = [], None
    for clip in found:
        audio, clip_rate = soundfile.read(clip.file, dtype="float32")
        rate = rate or clip_rate
        pieces += [audio, numpy.zeros(int(rate * clip.pause_after), dtype="float32")]
    whole = numpy.concatenate(pieces)
    soundfile.write(target, whole, rate, format="MP3")
    return len(whole) / rate


def assemble(run_date: date, *, root: Path = ROOT) -> AssembleResult:
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"
    folder = out_folder(root, run_date)

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if 9 not in done:
                raise AssembleError(f"There is no checked script for {run_date}. Run step 9 first.")
            if STEP in done:
                return AssembleResult(run.id, run_date, "already_done", folder, 0, report)
            if VOICE_STEP not in done:
                runlog.skip_step(conn, run.id, VOICE_STEP, "Step 10 was not run, so there is no audio.")
            runlog.begin_step(conn, run.id, STEP)

            episode = episodes.get(conn, run.id)
            told, _ = gather(conn, run.id)
            pages = {
                "newsletter.md": newsletter_page(run.run_date, episode, told),
                "show-notes.md": notes_page(run.run_date, told),
            }
            for name, lines in pages.items():
                (folder / name).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

            # The audio: the clips from step 10, joined. The clips are deleted once the episode file exists.
            spoken_clips = [clip for clip in clips.of_run(conn, run.id) if Path(clip.file).exists()]
            audio = ""
            if spoken_clips:
                seconds = join_clips(spoken_clips, folder / "episode.mp3")
                episodes.set_audio(conn, episode.id, seconds)
                for clip in spoken_clips:
                    Path(clip.file).unlink()
                clip_folder = folder / "clips"
                if clip_folder.exists() and not any(clip_folder.iterdir()):
                    clip_folder.rmdir()
                audio = f", and an episode of {seconds / 60:.1f} minutes"
            # The longer episodes are joined the same way. Imported here because that module uses step 10's helpers.
            from steps.formats.voice import join_formats
            longer = join_formats(conn, root, run, folder)
            in_episode = sum(story.entry.form in ("full", "brief") for story in told)
            summary = f"newsletter and show notes written with {in_episode} stories{audio}" + "".join(f", and {one}" for one in longer)
            runlog.finish_step(conn, run.id, STEP, detail=summary)
    except SQLAlchemyError as exc:
        raise AssembleError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    write_report(root, run_date, STEP, [
        f"# Step 11, Assemble: {run_date.isoformat()}",
        "",
        f"{summary}.",
        "",
        "Both are built by template from the sentences that passed step 9, the same ones the script holds. Nothing is added and nothing is reordered.",
        "",
        f"- `{folder / 'script.md'}` (written by step 9)",
        *(f"- `{folder / name}`" for name in pages),
        "",
        f"- `{folder / 'episode.mp3'}`" if audio else "No episode audio: step 10 did not speak this run.",
        *(f"- `{folder / about['audio']}`" for about in formats.FORMATS.values() if any(about["name"] + " episode" in one for one in longer)),
    ])
    return AssembleResult(run.id, run_date, "assembled", folder, in_episode, report)
