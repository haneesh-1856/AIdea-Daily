"""Run step 3 on its own: python -m steps.step03_clean_store [--date YYYY-MM-DD]"""

import argparse
import sys
from datetime import date

from steps.step03_clean_store.step import CleanError, clean_store


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 3, Clean and store: save what is new and relevant.")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="run date, default today")
    args = parser.parse_args()

    try:
        result = clean_store(args.date)
    except CleanError as exc:
        print(f"Run stopped at step 3.\n{exc}", file=sys.stderr)
        return 1

    if result.state == "already_done":
        print(f"{result.run_date}: run {result.run_id}, step 3 was already done; nothing was stored again")
    else:
        print(f"{result.run_date}: run {result.run_id}, {result.kept} items kept, {result.new} new")
    print(f"Report: {result.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
