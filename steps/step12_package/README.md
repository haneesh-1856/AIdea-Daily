# Step 12, Package and log

Hands the day's outputs over for review and records what happened. No model, no cost.

## What it does

1. Writes `out/<date>/review.md`: the status, a suggested title and description, every story and how it ended up, the sources used, every sentence the check removed, failures, cost, and each step's result.
2. Gives the run its final status, done or held, and records its cost.

## Rules

- **Nothing is published or uploaded.** Publishing is yours.
- **The review sheet shows every removed sentence,** so you know where to look.
- **A held run is finished, not left open.** A second trigger does not write it again; `--force` starts a fresh attempt.

## Run it

`.\.venv\Scripts\python.exe -m steps`

Tests: `.\.venv\Scripts\python.exe -m pytest steps/test_outputs.py`

## Not built

- **Telling you the package is ready** other than on screen. A message to your phone is proposed in the design.
- **Saving the database to a private repository.** That comes with the move to the cloud.
