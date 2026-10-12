"""Run step 4 on its own: python -m steps.step04_group [--date YYYY-MM-DD]"""

import argparse
import sys
from datetime import date

from steps.step04_group.step import GroupError, group


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 4, Group: merge items about the same event into stories.")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="run date, default today")
    args = parser.parse_args()

    try:
        result = group(args.date)
    except GroupError as exc:
        print(f"Run stopped at step 4.\n{exc}", file=sys.stderr)
        return 1

    if result.state == "already_done":
        print(f"{result.run_date}: run {result.run_id}, step 4 was already done; nothing was grouped again")
    else:
        print(
            f"{result.run_date}: run {result.run_id}, {result.items} items, "
            f"{result.new_stories} new stories, {result.joined} items joined an earlier story"
        )
    print(f"Report: {result.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
