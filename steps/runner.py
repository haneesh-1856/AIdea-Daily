"""The daily run: one program that runs the steps in order. A step already done is skipped, so a rerun resumes."""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError

from common import db, runlog
from common.settings import ROOT, SettingsError, database_url
from steps.step01_start.step import StartError, start
from steps.step02_fetch.step import FetchError, fetch
from steps.step03_clean_store.step import CleanError, clean_store
from steps.step04_group.step import GroupError, group
from steps.step05_score.step import ScoreError, score
from steps.step06_select.step import SelectError, select
from steps.step07_plan.step import PlanError, plan
from steps.step08_write.step import WriteError, write
from steps.step09_check_fit.step import CheckError, check_fit
from steps.step10_voice.step import VoiceError, voice
from steps.step11_assemble.step import AssembleError, assemble
from steps.step12_package.step import PackageError, package

STEPS: dict[int, Callable] = {
    2: fetch, 3: clean_store, 4: group, 5: score, 6: select, 7: plan, 8: write, 9: check_fit, 10: voice, 11: assemble,
    12: package,
}
REPEATABLE = (9, 10, 11, 12)
STOPS = (
    SettingsError, StartError, FetchError, CleanError, GroupError, ScoreError, SelectError, PlanError, WriteError,
    CheckError, VoiceError, AssembleError, PackageError,
)


def run_day(
    run_date: date, *, until: int = 12, force: bool = False, root: Path = ROOT, out=print, checks=None, ask=None, embed=None,
    speak=None, again: int | None = None,
) -> bool:
    """Run steps 1 to `until`. Returns False if a step stopped the run.

    `checks`, `ask`, `embed` and `speak` replace step 1's checks and the models; tests use them, a real run leaves them out.
    """
    if again:
        # Steps 9 to 12 cost nothing to repeat: they only work on what step 8 wrote. Earlier steps are never reopened
        # this way, because repeating them would fetch, rate or write again.
        with db.connect(database_url(root)).begin() as conn:
            run = runlog.latest_run(conn, run_date)
            if run is None or again - 1 not in runlog.done_steps(conn, run.id):
                out(f"There is no run for {run_date} that got as far as step {again - 1}, so there is nothing to repeat.")
                return False
            runlog.reopen(conn, run.id, again)
    extras = {4: {"embed": embed, "ask": ask}, 5: {"ask": ask}, 8: {"ask": ask}, 10: {"speak": speak}}
    number = 1
    try:
        result = start(run_date, force=force, root=root, checks=checks)
        out(f"Step 1, start: {result.state.replace('_', ' ')} (run {result.run_id}, attempt {result.attempt})")
        if result.state == "already_done":
            out(f"The run for {run_date} is finished. Use --force to run it again.")
            return True
        for number in (step for step in STEPS if step <= until):
            result = STEPS[number](run_date, root=root, **extras.get(number, {}))
            out(f"Step {number}, {runlog.STEPS[number]}: {_detail(root, run_date, number) or result.state.replace('_', ' ')}")
    except STOPS as exc:
        _record_failure(root, run_date, number, str(exc))
        out(f"\nThe run stopped at step {number}, {runlog.STEPS[number]}.\n{exc}")
        return False

    out(f"\nReport of the last step: {result.report}")
    if number == 12:
        out(f"The package is {'HELD, read review.md first' if result.status == 'held' else 'ready for your review'}: {result.folder}")
    return True


def _detail(root: Path, run_date: date, number: int) -> str | None:
    with db.connect(database_url(root)).connect() as conn:
        run = runlog.latest_run(conn, run_date)
        return next((row.detail for row in runlog.steps_of(conn, run.id) if row.step == number), None)


def _record_failure(root: Path, run_date: date, number: int, reason: str) -> None:
    """Every run is logged, including failed ones. A step that stopped before it began is recorded here."""
    try:
        with db.connect(database_url(root)).begin() as conn:
            run = runlog.latest_run(conn, run_date)
            if run and number not in runlog.done_steps(conn, run.id):
                runlog.begin_step(conn, run.id, number)
                runlog.finish_step(conn, run.id, number, "failed", reason)
    except (SQLAlchemyError, SettingsError):
        pass  # the failure is already being reported on screen; a second error here must not hide it


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the day's steps in order, resuming where an earlier run stopped.")
    parser.add_argument("until", type=int, nargs="?", default=12, choices=[1, *STEPS], help="the last step to run, default 12")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="run date, default today")
    parser.add_argument("--force", action="store_true", help="start a fresh attempt even if the date's run exists")
    parser.add_argument("--again", type=int, choices=REPEATABLE, metavar="STEP",
                        help="repeat the run from this step (9, 10, 11 or 12) on what was already written; costs nothing")
    args = parser.parse_args()
    # Story titles contain characters the Windows console cannot print in its default encoding.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return 0 if run_day(args.date, until=args.until, force=args.force, again=args.again) else 1
