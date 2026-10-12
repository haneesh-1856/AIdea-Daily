"""Run step 2 on its own: python -m steps.step02_fetch [--date YYYY-MM-DD]"""

import argparse
import sys
from datetime import date

from steps.step02_fetch.step import FetchError, fetch


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 2, Fetch: read every source once.")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="run date, default today")
    args = parser.parse_args()

    try:
        result = fetch(args.date)
    except FetchError as exc:
        print(f"Run stopped at step 2.\n{exc}", file=sys.stderr)
        return 1

    if result.state == "already_done":
        print(f"{result.run_date}: run {result.run_id}, step 2 was already done; nothing was fetched again")
    else:
        print(f"{result.run_date}: run {result.run_id}, fetched")
    print(f"Entries: {len(result.entries)} in {result.entries_file}")
    print(f"Report: {result.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
