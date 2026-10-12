"""Step 12, Package and log: hand the day's outputs over for review and record what happened. Nothing is published."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from common import db, episodes, health, model, runlog, script
from common.report import step_folder, write_report
from common.settings import ROOT, database_url
from steps.step11_assemble.step import KINDS, NOTHING_TODAY, gather, long_date, out_folder

STEP = 12


class PackageError(Exception):
    """The step could not run. The message says why."""


@dataclass
class PackageResult:
    run_id: int
    run_date: date
    state: str  # packaged, already_done
    status: str  # ready, held
    folder: Path
    cost: float
    report: Path


def package(run_date: date, *, root: Path = ROOT) -> PackageResult:
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"
    folder = out_folder(root, run_date)

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if STEP - 1 not in done:
                raise PackageError(f"The outputs for {run_date} are not built. Run step 11 first.")
            episode = episodes.get(conn, run.id)
            if STEP in done:
                return PackageResult(run.id, run_date, "already_done", episode.status, folder, run.cost or 0.0, report)
            runlog.begin_step(conn, run.id, STEP)

            told, _ = gather(conn, run.id)
            spent = model.spent(conn, run.id)
            lines = _review_lines(run, episode, told, script.log_of(conn, run.id), health.failed_sources(conn, run.id), spent)
            runlog.finish_step(conn, run.id, STEP, detail=f"review sheet written, run {episode.status}")
            lines += _steps_table(runlog.steps_of(conn, run.id))
            (folder / "review.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            # The day's scoring table goes into the package too, so that it is beside what it led to.
            scoring = step_folder(root, run_date, 5) / "report.md"
            if scoring.exists():
                (folder / "scoring.md").write_text(scoring.read_text(encoding="utf-8"), encoding="utf-8")
            # The run gets its final status here: done, or held when the check failed too often.
            runlog.finish_run(conn, run.id, "held" if episode.status == "held" else "done", spent[3])
    except SQLAlchemyError as exc:
        raise PackageError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    write_report(root, run_date, STEP, [
        f"# Step 12, Package and log: {run_date.isoformat()}",
        "",
        f"The package is {'HELD: read the review sheet first' if episode.status == 'held' else 'ready for your review'}.",
        "",
        f"- Folder: `{folder}`",
        "- Files: " + ("`episode.mp3`, " if episode.audio_seconds else "") + "`script.md`, `newsletter.md`, `show-notes.md`, `review.md`, `scoring.md`",
        f"- Model cost for the run: ${spent[3]:.4f}",
        "",
        "Nothing has been published or uploaded. Publishing is yours.",
    ])
    return PackageResult(run.id, run_date, "packaged", episode.status, folder, spent[3], report)


def _review_lines(run, episode, told: list, log: list, failed_sources: list, spent: tuple) -> list[str]:
    day = run.run_date
    shown = [story for story in told if story.entry.form in ("full", "brief")]
    headlines = [story.text["headline"] for story in shown if story.text["headline"]]
    title = f"AI news, {long_date(day)}" + (f": {headlines[0].rstrip('.')}" if headlines else "")
    outlets = sorted({row.source for story in shown for row in story.sources})
    requests, tokens_in, tokens_out, cost = spent

    lines = [f"# Review sheet: {long_date(day)}", ""]
    if episode.status == "held":
        held = next((entry.reason for entry in log if entry.action == "held"), "too many sentences failed the check")
        lines += [f"**HELD.** {held[0].upper() + held[1:]}. Read the removed sentences below before using anything.", ""]
    else:
        lines += ["**Ready for your review.**", ""]
    lines += [
        "Nothing has been published or uploaded. Editing, checking again and publishing are yours.",
        "",
        "## Suggested title and description",
        "",
        f"**Title:** {title}",
        "",
        f"**Description:** {' '.join(headlines) or NOTHING_TODAY}",
        "",
        "## In this folder",
        "",
        *([f"- `episode.mp3`: the spoken episode, {episode.audio_seconds / 60:.1f} minutes, in the voice of the reference recording"] if episode.audio_seconds else []),
        "- `script.md`: the podcast script, checked and fitted to length",
        "- `newsletter.md`: the same stories for reading",
        "- `show-notes.md`: every story's links and confidence label",
        "",
        f"## Stories ({len(shown)} in the episode, {episode.words} words of a cap of {episode.word_cap})",
        "",
        "| # | Story | In the episode as | Label | Kind | Score |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {story.entry.position} | {story.entry.title.replace('|', '/')} | {story.entry.form} | {story.entry.label} | "
        f"{KINDS[story.entry.kind]} | {story.entry.score:g} |"
        for story in told
    ]
    left_out = [story for story in told if story.entry.form == "dropped"]
    if left_out:
        lines += ["", "## Left out of the episode", ""]
        lines += [f"- **{story.entry.title}**: {story.entry.reason}" for story in left_out]
    lines += ["", "## Sources used", "", ", ".join(outlets) or "None."]

    removed = [entry for entry in log if entry.action == "removed"]
    lines += ["", f"## Sentences the check removed ({len(removed)})", ""]
    lines += [f"- **{entry.title or 'Linking part'}**: \"{entry.text}\" ({entry.reason})" for entry in removed] or ["None."]
    shortened = [entry for entry in log if entry.action == "shortened to brief"]
    if shortened:
        lines += ["", "## Stories shortened to their brief version", ""]
        lines += [f"- **{entry.title}**: {entry.reason}" for entry in shortened]

    lines += ["", "## Failures", ""]
    lines += [f"- Source {row.source} did not answer: {row.error}" for row in failed_sources] or ["No source failed."]
    lines += [
        "",
        "## Cost",
        "",
        f"{requests} model requests, {tokens_in} tokens read, {tokens_out} tokens written, ${cost:.4f}.",
    ]
    return lines


def _steps_table(steps: list) -> list[str]:
    lines = ["", "## The run, step by step", "", "| Step | Result | Detail |", "| --- | --- | --- |"]
    lines += [f"| {row.step} {row.name} | {row.status} | {(row.detail or '').replace('|', '/')} |" for row in steps]
    return lines
