"""Step 8, Write: the model writes each story and the linking parts, from the supplied text only."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from common import db, episodes, formats, model, runlog, script, selections, stories
from common.report import step_folder, write_report
from common.settings import ROOT, database_url
from common.text import sentences, word_count
from steps.step08_write import prompts

STEP = 8
NOTHING_TODAY = "No story met the bar today."


class WriteError(Exception):
    """The step could not run, or nothing could be written. The message says why."""


@dataclass
class WriteResult:
    run_id: int
    run_date: date
    state: str  # written, already_done
    written: int
    set_aside: int  # stories the model flagged, or failed on
    cost: float
    report: Path


def spoken_date(day: date) -> str:
    return f"{day:%A}, {day.day} {day:%B %Y}"


def cut(text: str, limit: int) -> str:
    words = text.split()
    return text if len(words) <= limit else " ".join(words[:limit])


def source_text(row, limit: int) -> tuple[str, str]:
    """The text to write from for one source, and what kind of text it is."""
    if row.article_status == "ok" and row.article_text:
        return cut(row.article_text, limit), "full article"
    return row.summary or "", "the feed's short description only; the full article could not be read"


def story_message(entry, sources: list, earlier: list, limit: int) -> str:
    parts = [
        f"Story: {entry.title}",
        f"Kind: {prompts.KINDS[entry.kind]}",
        f"Confidence label: {prompts.LABELS[entry.label]}",
    ]
    if earlier:
        parts.append("Already reported:")
        parts += [f"- {row.run_date.isoformat()}: {row.what_happened}" for row in earlier]
    for number, row in enumerate(sources, 1):
        text, what = source_text(row, limit)
        published = f"\nPublished: {row.published_at:%Y-%m-%d}" if row.published_at else ""
        parts.append(f"\nSource {number}: {row.source} ({row.kind})\nTitle: {row.title}{published}\nText ({what}):\n{text}")
    return "\n".join(parts)


def names_list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def spoken_title(title: str) -> str:
    """The story's title as the narrator reads it before the story."""
    title = title.strip()
    return title if title[-1:] in ".!?" else title + "."


def intro(kind: str, label: str, first_seen: date | None = None) -> str:
    """What the narrator adds after a story's title, only when the listener needs it: that the story is an update
    or a correction, that it began on an earlier day, or that it is unconfirmed. Usually nothing. Made by code.

    The sources and the confidence label of every story are in the show notes and the newsletter.
    """
    said = []
    if kind != "new":
        said.append({"update": "An update to a story covered before.", "correction": "A correction to a story covered before."}[kind])
    elif first_seen:
        said.append(f"This first emerged on {first_seen:%A}.")
    if label == "rumour":
        said.append("This one is unconfirmed.")
    return " ".join(said)


def write(run_date: date, *, root: Path = ROOT, ask: model.Ask | None = None) -> WriteResult:
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if STEP - 1 not in done:
                raise WriteError(f"There is no outline for {run_date}. Run step 7 first.")
            if STEP in done:
                return WriteResult(run.id, run_date, "already_done", 0, 0, 0.0, report)

            # The run's frozen settings are used, not the files, with one exception: a run started before a
            # model was chosen takes the model from settings.toml as it is now, so that the run can resume here.
            settings = {**run.settings, "model": model.chosen(run.settings, root)}
            lineup = episodes.lineup(conn, run.id)
            word_cap = episodes.get(conn, run.id).word_cap
            if lineup and ask is None:
                if not model.configured(settings["model"]):
                    raise WriteError(
                        "No model is chosen, so nothing can be written. Set provider and name under [model] in "
                        "settings.toml, set the key in the environment, and run again: the run resumes at this step."
                    )
                ask = model.ask
            runlog.begin_step(conn, run.id, STEP)
            # Stories the model failed on in an earlier try are tried again; everything else is kept, never rewritten.
            script.forget_failed(conn, run.id)
            have = script.summaries_of(conn, run.id)
            material = {}
            for entry in lineup:
                sources = selections.sources(conn, entry.item_ids)
                earlier = selections.earlier_reports(conn, entry.story_id, entry.thread_id, run.run_date)
                material[entry.story_id] = (sources, earlier)

        for entry in lineup:
            if entry.story_id in have:
                continue
            # Each story is told how long it may be: that follows its score.
            target, most = episodes.story_room(entry, settings, word_cap, len(lineup))
            rules = prompts.STORY_RULES.format(count=len(lineup), target=target, max_words=most)
            sources, earlier = material[entry.story_id]
            message = story_message(entry, sources, earlier, settings["write"]["max_source_words"])
            stray = []
            try:
                reply = ask(settings["model"], rules, message, prompts.STORY_ANSWER)
            except model.ModelError as exc:
                values, reply = {"flag": "failed", "note": str(exc)}, None
            else:
                values = _summary_values(reply.data, entry.kind)
                stray = [] if values.get("flag") else _left_out(reply.data, sources)
            if stray:
                # The story is told from the sources that report it. The others are not its sources any more.
                sources = [row for row in sources if row not in stray]
                material[entry.story_id] = (sources, earlier)
                values["note"] = (f"written without {names_list([row.source for row in stray])}, "
                                  f"which {'reports' if len(stray) == 1 else 'report'} a different event and "
                                  f"{'goes' if len(stray) == 1 else 'go'} back to be grouped again")
            elif values.get("flag") == "different_events" and entry.kind != "new":
                # Today's sources are about something other than the story they were filed under. The story keeps
                # what it had; these go back to be grouped again, so that what they report is not lost.
                stray = list(sources)
            # Each story is saved as soon as it is written, so a run that stops here loses nothing it paid for.
            with engine.begin() as conn:
                if stray:
                    if not values.get("flag"):
                        selections.keep_sources(conn, run.id, entry.story_id, [row.id for row in sources])
                    stories.split_off(conn, run.id, entry.story_id, [row.id for row in stray], "the writer found it reports a different event")
                script.save_summary(conn, run.id, entry.story_id, **values)
                if reply:
                    model.record(conn, run.id, STEP, "story", reply, entry.story_id)

        with engine.begin() as conn:
            have = script.summaries_of(conn, run.id)
        written = [entry for entry in lineup if have[entry.story_id].flag is None]
        if lineup and all(have[entry.story_id].flag == "failed" for entry in lineup):
            with engine.begin() as conn:
                runlog.finish_step(conn, run.id, STEP, "failed", "the model failed on every story")
            raise WriteError(f"The model failed on every story. The first error: {have[lineup[0].story_id].note}")

        linking, linking_reply, linking_error = _linking(run.run_date, written, have, settings, ask)

        with engine.begin() as conn:
            if linking_reply:
                model.record(conn, run.id, STEP, "linking", linking_reply)
            lines = _script_lines(written, have, material, linking)
            script.replace_lines(conn, run.id, lines)

        # The longer episodes are written last, from the same stories and sources. Imported here because that
        # module uses this one's helpers.
        from steps.formats.write import write_formats
        longer = write_formats(engine, run, settings, written, have, material, ask)

        with engine.begin() as conn:
            requests, tokens_in, tokens_out, cost = model.spent(conn, run.id, STEP)
            summary = (f"{len(written)} stories written, {len(lineup) - len(written)} set aside, "
                       + "".join(f"{one}, " for one in longer) + f"{requests} requests, ${cost:.4f}")
            report_lines = _report_lines(run_date, summary, lineup, have, linking_error, settings, (requests, tokens_in, tokens_out, cost))
            report_lines += _formats_lines(conn, run.id, settings)
            runlog.finish_step(conn, run.id, STEP, detail=summary)
    except SQLAlchemyError as exc:
        raise WriteError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    write_report(root, run_date, STEP, report_lines)
    return WriteResult(run.id, run_date, "written", len(written), len(lineup) - len(written), cost, report)


def _left_out(data: dict, sources: list) -> list:
    """The sources the writer did not use because they report a different event. At least one source is always kept:
    an answer that leaves every source out is ignored, since the story was written from something."""
    numbers = {number for number in data.get("left_out") or [] if isinstance(number, int) and 1 <= number <= len(sources)}
    return [] if len(numbers) >= len(sources) else [sources[number - 1] for number in sorted(numbers)]


def _summary_values(data: dict, kind: str) -> dict:
    """What to store for one story from the model's answer."""
    if data.get("different_events") is True:
        return {"flag": "different_events", "note": data.get("note") or "the sources describe different events"}
    # Only a story covered before can have nothing new.
    if data.get("nothing_new") is True and kind != "new":
        return {"flag": "nothing_new", "note": data.get("note") or "today's sources add nothing new"}
    values = {
        "headline": (data.get("headline") or "").strip(),
        "what_happened": (data.get("what_happened") or "").strip(),
        "differences": (data.get("how_sources_see_it") or "").strip(),
        "brief": (data.get("brief") or "").strip(),
    }
    if not values["headline"] or not values["what_happened"]:
        return {"flag": "failed", "note": "the model returned no headline or no account of what happened"}
    return values


def _linking(day: date, written: list, have: dict, settings: dict, ask) -> tuple[dict, model.Reply | None, str | None]:
    """The opening, watch list and closing. If the model cannot be asked, plain ones made by code are used."""
    plain = {"opening": f"This is your AI news briefing for {spoken_date(day)}.", "watch_list": "", "closing": "That is all for today."}
    if not written:
        return dict(plain, opening=f"{plain['opening']} {NOTHING_TODAY}"), None, None
    message = f"Date: {spoken_date(day)}\n\nStories in running order:\n" + "\n".join(
        f"{number}. {have[entry.story_id].headline}\n   Brief: {have[entry.story_id].brief}" for number, entry in enumerate(written, 1)
    )
    try:
        reply = ask(settings["model"], prompts.LINKING_RULES, message, prompts.LINKING_ANSWER)
    except model.ModelError as exc:
        return plain, None, str(exc)
    answer = {key: (reply.data.get(key) or "").strip() for key in plain}
    return {key: answer[key] or plain[key] for key in plain}, reply, None


def _script_lines(written: list, have: dict, material: dict, linking: dict) -> list[dict]:
    """The draft script, one sentence per line, in speaking order. Brief versions are stored beside the full ones."""
    lines = [{"part": "opening", "text": text} for text in sentences(linking["opening"])]
    lines += [{"part": "headline", "story_id": entry.story_id, "text": have[entry.story_id].headline} for entry in written]
    for entry in written:
        summary = have[entry.story_id]
        lines.append({"part": "title", "story_id": entry.story_id, "text": spoken_title(entry.title)})
        lines += [{"part": "intro", "story_id": entry.story_id, "text": text} for text in sentences(intro(entry.kind, entry.label, entry.first_seen))]
        # "Coverage broadly agrees." is what the writer says when there is nothing to compare, also for a story with
        # one source. Said after nearly every story it was the episode's most repeated line, and wrong for a single
        # source, so it is left out of the script; the story's what happened stands on its own.
        how = "" if summary.differences == "Coverage broadly agrees." else summary.differences
        for part, text in (("what", summary.what_happened), ("how", how), ("brief", summary.brief)):
            lines += [{"part": part, "story_id": entry.story_id, "text": sentence} for sentence in sentences(text)]
    lines += [{"part": "watch", "text": text} for text in sentences(linking["watch_list"])]
    lines += [{"part": "closing", "text": text} for text in sentences(linking["closing"])]
    return lines


def _formats_lines(conn, run_id: int, settings: dict) -> list[str]:
    """The plan of each longer episode and how much of it is written."""
    lines = []
    for name, row in formats.scripts_of(conn, run_id).items():
        if name not in formats.wanted(settings):
            continue
        lines += ["", f"## The {formats.FORMATS[name]['name']} ({formats.FORMATS[name]['label']})", ""]
        lines += [f"Not finished: {row.note}", ""] if row.note else []
        lines += [f"Shorter than wanted: {row.shortfall}", ""] if row.shortfall else []
        lines += ["| # | Segment | Stories | Words planned | Words written |", "| --- | --- | --- | --- | --- |"]
        lines += [
            f"| {segment.position} | {segment.title.replace('|', '/')} | {len(segment.story_ids)} | {segment.words} | "
            f"{formats.spoken_words(segment.lines) if segment.lines else 'not written'} |"
            for segment in formats.segments_of(conn, run_id, name)
        ]
    return lines


def _report_lines(run_date: date, summary: str, lineup: list, have: dict, linking_error: str | None, settings: dict, spent: tuple) -> list[str]:
    requests, tokens_in, tokens_out, cost = spent
    said = {"different_events": "set aside: the sources describe different events", "nothing_new": "set aside: nothing new since it was last reported",
            "failed": "failed: the model gave no usable answer"}
    lines = [
        f"# Step 8, Write: {run_date.isoformat()}",
        "",
        f"{summary}.",
        "",
        "This is the draft. Nothing here has been checked against the sources yet; step 9 does that.",
        "",
        "| | |",
        "| --- | --- |",
        f"| Model | {settings['model'].get('name') or 'none'} |",
        f"| Requests | {requests} |",
        f"| Tokens read | {tokens_in} |",
        f"| Tokens written | {tokens_out} |",
        f"| Cost | ${cost:.4f} |",
        "",
    ]
    if linking_error:
        lines += [f"The opening and closing were made by code, because the request for them failed: {linking_error}", ""]
    lines += ["| # | Story | Result | Full words | Brief words |", "| --- | --- | --- | --- | --- |"]
    for entry in lineup:
        row = have[entry.story_id]
        full = word_count(row.what_happened) + word_count(row.differences)
        result = said[row.flag] + (f" ({row.note})" if row.note else "") if row.flag else (row.note or "written")
        lines.append(f"| {entry.position} | {entry.title.replace('|', '/')} | {result.replace('|', '/')} | {full} | {word_count(row.brief)} |")
    for entry in lineup:
        row = have[entry.story_id]
        if row.flag is None:
            lines += ["", f"## {entry.position}. {row.headline}", "", f"**What happened.** {row.what_happened}", "",
                      f"**How sources see it.** {row.differences}", "", f"**Brief.** {row.brief}"]
    return lines
