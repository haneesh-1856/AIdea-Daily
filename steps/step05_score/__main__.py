"""Run step 5 on its own: python -m steps.step05_score [--date YYYY-MM-DD]"""

import argparse
import sys
from datetime import date

from steps.step05_score.step import ScoreError, score


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 5, Score: rank each story by its evidence.")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="run date, default today")
    args = parser.parse_args()

    try:
        result = score(args.date)
    except ScoreError as exc:
        print(f"Run stopped at step 5.\n{exc}", file=sys.stderr)
        return 1

    if result.state == "already_done":
        print(f"{result.run_date}: run {result.run_id}, step 5 was already done; nothing was scored again")
    else:
        print(f"{result.run_date}: run {result.run_id}, {result.stories} stories scored")
    print(f"Report: {result.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
