"""Step 1, Start: decide whether a run should happen and get everything ready for it."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import httpx
from sqlalchemy.exc import SQLAlchemyError

from common import articles, db, formats, model, runlog
from common.report import write_report
from common.settings import ROOT, database_url, load

STEP = 1
Check = tuple[str, Callable[[], str | None]]


class StartError(Exception):
    """The run cannot start. The message says why."""


@dataclass
class StartResult:
    run_id: int
    run_date: date
    attempt: int
    state: str  # new, resumed, already_done
    next_step: int | None
    settings: dict
    report: Path


def check_internet() -> str | None:
    """Returns None when the internet is reachable, else what went wrong."""
    try:
        httpx.head("https://hn.algolia.com", timeout=10)
    except httpx.HTTPError as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


AUDIO_FILES = ("episode.mp3", *(about["audio"] for about in formats.FORMATS.values()))


def delete_old_audio(root: Path, today: date, keep_days: int) -> int:
    """Delete episode audio older than the retention period. The script, newsletter and notes are kept."""
    deleted = 0
    for folder in (root / "out").glob("*"):
        try:
            made = date.fromisoformat(folder.name)
        except ValueError:
            continue
        for name in AUDIO_FILES:
            audio = folder / name
            if audio.exists() and (today - made).days > keep_days:
                audio.unlink()
                deleted += 1
    return deleted


DEFAULT_CHECKS: list[Check] = [("Internet connection", check_internet)]


def start(
    run_date: date,
    *,
    force: bool = False,
    root: Path = ROOT,
    checks: list[Check] | None = None,
) -> StartResult:
    settings = load(root)
    url = database_url(root)

    failures = []
    check_lines = []
    all_checks = list(DEFAULT_CHECKS if checks is None else checks)
    if model.configured(settings["model"]):
        all_checks.append(("Model key", lambda: model.check(settings["model"])))
    for name, check in all_checks:
        problem = check()
        check_lines.append(f"| {name} | {'Failed: ' + problem if problem else 'OK'} |")
        if problem:
            failures.append(f"{name}: {problem}")
    if failures:
        raise StartError("A check failed before the run began:\n" + "\n".join(failures))
    if not model.configured(settings["model"]):
        check_lines.append("| Model key | Not needed: no model is chosen, so the run will stop at step 8 |")

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            if run is None or force:
                run = runlog.create_run(conn, run_date, settings)
                runlog.begin_step(conn, run.id, STEP)
                keep = timedelta(days=settings["retention"]["article_text_days"])
                cleared = articles.clear_old_text(conn, datetime.now(timezone.utc) - keep)
                check_lines.append(f"| Old article text | {cleared} cleared after {keep.days} days |")
                audio_days = settings["retention"]["audio_days"]
                check_lines.append(f"| Old episode audio | {delete_old_audio(root, run_date, audio_days)} deleted after {audio_days} days |")
                runlog.finish_step(conn, run.id, STEP)
                state = "new"
            elif run.status in ("done", "held"):
                state = "already_done"
            else:
                state = "resumed"
            upcoming = runlog.next_step(conn, run.id)
    except SQLAlchemyError as exc:
        raise StartError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    # A resumed or finished run keeps the settings it started with, even if the files have changed since.
    frozen = run.settings
    report = write_report(root, run_date, STEP, _report_lines(run, state, upcoming, frozen, url, check_lines))
    return StartResult(run.id, run_date, run.attempt, state, upcoming, frozen, report)


def _report_lines(run, state: str, upcoming: int | None, settings: dict, url: str, check_lines: list[str]) -> list[str]:
    outcome = {
        "new": "A new run was started.",
        "resumed": "Today's run was already started and is not finished, so it continues where it stopped.",
        "already_done": "Today's run is already finished. Nothing was done. Use --force to run it again.",
    }[state]
    next_line = f"Step {upcoming}, {runlog.STEPS[upcoming]}" if upcoming else "None; every step is done"
    kinds = {}
    for feed in settings["feeds"]:
        kinds[feed["kind"]] = kinds.get(feed["kind"], 0) + 1
    return [
        f"# Step 1, Start: {run.run_date.isoformat()}",
        "",
        outcome,
        "",
        "| | |",
        "| --- | --- |",
        f"| Run number | {run.id} |",
        f"| Attempt for this date | {run.attempt} |",
        f"| Run started (UTC) | {run.started_at.strftime('%Y-%m-%d %H:%M:%S')} |",
        f"| Next step | {next_line} |",
        f"| Database | {db.describe(url)} |",
        "",
        "## Checks",
        "",
        "| Check | Result |",
        "| --- | --- |",
        *check_lines,
        "",
        "## Settings frozen for this run",
        "",
        "| Setting | Value |",
        "| --- | --- |",
        f"| Sources | {len(settings['feeds'])} feeds: " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) + " |",
        f"| Ignore items older than | {settings['collect']['max_age_days']} days |",
        f"| Hacker News minimum points | {settings['collect']['hn_min_points']} |",
        f"| AI keywords | {len(settings['collect']['ai_keywords'])} |",
        f"| Model | {settings['model'].get('name') or 'none chosen'} |",
        f"| Episode length cap | {settings['episode']['length_minutes']} minutes |",
        f"| Speaking pace | {settings['episode']['words_per_minute']} words a minute |",
        f"| Keep article text | {settings['retention']['article_text_days']} days |",
        f"| Keep audio | {settings['retention']['audio_days']} days |",
    ]
