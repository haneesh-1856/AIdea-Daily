"""Run step 1 on its own: python -m steps.step01_start [--date YYYY-MM-DD] [--force]"""

import argparse
import sys
from datetime import date

from common import runlog
from common.settings import SettingsError
from steps.step01_start.step import StartError, start


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 1, Start: open or resume the day's run.")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="run date, default today")
    parser.add_argument("--force", action="store_true", help="start a fresh attempt even if today's run exists")
    args = parser.parse_args()

    try:
        result = start(args.date, force=args.force)
    except (SettingsError, StartError) as exc:
        print(f"Run stopped at step 1.\n{exc}", file=sys.stderr)
        return 1

    upcoming = f"step {result.next_step}, {runlog.STEPS[result.next_step]}" if result.next_step else "nothing, the run is finished"
    print(f"{result.run_date}: run {result.run_id}, attempt {result.attempt}, {result.state.replace('_', ' ')}")
    print(f"Next: {upcoming}")
    print(f"Report: {result.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
