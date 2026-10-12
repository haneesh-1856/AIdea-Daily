"""Step 9's part of the longer episodes: compare each script with the sources, and write it out as a page.

The regular script loses a sentence that fails the check. A conversation cannot lose a sentence without breaking,
so here a failing sentence is kept and listed for the owner to look at before the episode is used."""

import re
from datetime import date
from pathlib import Path

from common import formats, selections
from common.facts import Pool, numbers_in, unsupported
from common.text import sentences

COUNTED_TO = 12  # a whole number up to this is everyday speech ("two things"), not a figure taken from a source


def unverified(sentence: str, pool: Pool) -> list[str]:
    """What a spoken sentence states that the sources do not contain: figures, and names inside the sentence.

    Talk opens sentences with words no source has ("Okay", "Imagine", "Honestly"), so a plain capitalised first
    word is not treated as a name here, and neither is "I'll" or "I'm".
    """
    text = formats.plain(sentence)
    text = re.sub(r"\bI(?=['’](?:ll|m|ve|d)\b)", "i", text)
    text = re.sub(r"^([\"'“‘]?)([A-Z])(?=[a-z'’]*\b)", lambda m: m.group(1) + m.group(2).lower(), text)
    small = {float(value) for value in numbers_in(text) if value == int(value) and 0 <= value <= COUNTED_TO}
    return [problem for problem in unsupported(text, pool) if not (problem.startswith("number ") and float(problem[7:]) in small)]


def flagged(segments: list, pools: dict, always: Pool) -> list[dict]:
    """Every sentence of the script that fails the check. A stories segment is checked against its own stories'
    sources; a linking segment may draw on any story of the day."""
    anything = always
    for pool in pools.values():
        anything |= pool
    found = []
    for segment in segments:
        pool = anything
        if segment.kind == "stories":
            pool = always
            for story_id in segment.story_ids:
                pool |= pools[story_id]
        for line in segment.lines:
            for sentence in sentences(formats.plain(line["text"])):
                problems = unverified(sentence, pool)
                if problems:
                    found.append({"segment": segment.position, "speaker": line["speaker"], "text": sentence, "problems": problems})
    return found


def clock(words: int, pace: int) -> str:
    seconds = round(words * 60 / pace)
    return f"{seconds // 60}:{seconds % 60:02d}"


def page(name: str, show: str, day: date, segments: list, row, sources: dict, pace: int) -> list[str]:
    """The script as a page to read and record from. Everything in a `>` line is a note and is not spoken."""
    about = formats.FORMATS[name]
    duo = len(about["speakers"]) > 1
    stories = sum(len(segment.story_ids) for segment in segments)
    lines = [f"# {show}: {day:%A}, {day.day} {day:%B %Y} ({about['label']})", ""]
    if duo:
        lines += ["Two-voice script. **HOST** runs the show and asks what a curious listener would ask. **GUEST** is the show's "
                  "AI analyst, who has read today's stories and explains them. A word in square brackets, such as `[surprised]`, "
                  "is a direction for how the line is said and is not read. Lines that begin with `>` are notes and sources: "
                  "they are not read either.", ""]
    else:
        lines += ["Presenter script. Everything in normal text is spoken. Lines that begin with `>` are notes and sources: "
                  "they are not read aloud.", ""]
    lines += [f"> **Built from:** the {stories} stories of the day's run and the source articles stored for them, the same ones "
              "the regular episode is written from.", "> **Runtime:** see the table at the end."]
    lines += [f"> **Shorter than wanted:** {row.shortfall}"] if row.shortfall else []
    lines += ["", "---", ""]
    for segment in segments:
        lines += [f"## {segment.position}. {segment.title}", ""]
        for line in segment.lines:
            lines += [f"**{line['speaker']}:** {line['text']}" if duo else line["text"], ""]
        for story_id in segment.story_ids:
            title, rows = sources[story_id]
            lines += [f"> **{title}:** " + ", ".join(f"[{one.source}]({one.url})" for one in rows)]
        lines += [""] if segment.story_ids else []

    words = [formats.spoken_words(segment.lines) for segment in segments]
    lines += ["---", "", "## Runtime", "", f"| Segment | Spoken words | At {pace} words a minute |", "| --- | --- | --- |"]
    lines += [f"| {segment.position}. {segment.title.replace('|', '/')} | {count} | {clock(count, pace)} |" for segment, count in zip(segments, words)]
    lines += [f"| **Total** | **{sum(words)}** | **{clock(sum(words), pace)}** |", ""]
    if duo:
        each = {speaker: sum(formats.spoken_words(segment.lines, speaker) for segment in segments) for speaker in about["speakers"]}
        lines += ["> " + " and ".join(f"{speaker} speaks {count} words" for speaker, count in each.items()) + ".", ""]

    found = row.flagged or []
    lines += [f"## Sentences to check before using this ({len(found)})", "",
              "> Each has a figure or a name that was not found in the sources of its segment. Some are harmless: a made-up "
              "example, or a word the check does not know. Nothing was removed.", ""]
    lines += [f"> - Segment {one['segment']}, {one['speaker']}: \"{one['text']}\" ({', '.join(one['problems'])})" for one in found] or ["> None."]
    made_up = list(dict.fromkeys(one for segment in segments for one in segment.illustrations or []))
    if made_up:
        lines += ["", "## Examples that are the writer's own, not the sources'", ""]
        lines += [f"> - {one}" for one in made_up]
    return lines


def check_formats(conn, folder: Path, run, lineup: list, pools: dict) -> tuple[list[str], list[str]]:
    """Check every finished longer script and write its page. Returns what to add to the step's summary, and to
    its report."""
    settings = run.settings
    said, report = [], []
    day = run.run_date
    for name in formats.wanted(settings):
        about = formats.FORMATS[name]
        file = folder / about["script"]
        row = formats.scripts_of(conn, run.id).get(name)
        segments = formats.segments_of(conn, run.id, name)
        report += ["", f"## The {about['name']} ({about['label']})", ""]
        if row is None or not formats.written(segments):
            # A page left by an earlier attempt at the day is not this run's script.
            file.unlink(missing_ok=True)
            report += [f"Not written: {row.note if row and row.note else 'step 8 made no script for it'}."]
            continue
        chosen = settings["formats"]
        # The show's name, the date and the count of stories may be said anywhere.
        always = Pool.of([chosen["show_name"], f"{day:%A %B %Y} {day.day} {len(lineup)}"])
        found = flagged(segments, pools, always)
        formats.update(conn, run.id, name, flagged=found)
        row = formats.scripts_of(conn, run.id)[name]
        by_story = {entry.story_id: entry for entry in lineup}
        sources = {story_id: (by_story[story_id].title, selections.sources(conn, by_story[story_id].item_ids))
                   for segment in segments for story_id in segment.story_ids}
        lines = page(name, chosen["show_name"], day, segments, row, sources, chosen["speaking_pace"])
        file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        words = sum(formats.spoken_words(segment.lines) for segment in segments)
        said.append(f"{about['name']} {words} words with {len(found)} sentences to check")
        report += [f"`{about['script']}`: {words} words, about {clock(words, chosen['speaking_pace'])} at "
                   f"{chosen['speaking_pace']} words a minute. {len(found)} sentences have a figure or a name not found in "
                   "their segment's sources. They are kept and listed at the end of the script: check them before using it.", ""]
        report += [f"- Segment {one['segment']}, {one['speaker']}: \"{one['text']}\" ({', '.join(one['problems'])})" for one in found]
    return said, report
