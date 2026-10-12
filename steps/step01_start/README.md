# Step 1, Start

Decides whether a run should happen and gets everything ready for it. It fetches no news and spends nothing.

## What it does

1. Reads `sources.toml` and `settings.toml` and checks every value.
2. Checks the internet connection.
3. Opens the database and creates its tables if they do not exist.
4. Opens today's run record, or picks up the one already there.
5. Writes a report to `runs/<date>/01_start/report.md`.

## Rules

- **One run per day.** If today's run is finished, nothing happens unless `--force` is given.
- **Resume, don't restart.** An unfinished run continues from its first step not yet done.
- **Settings are frozen.** A run keeps the settings it started with, even if the files change later.
- **Fail early.** A bad setting or a failed check stops the run before a run record is written.
- **A forced rerun is a new attempt.** The earlier attempt stays in the database.

## It never

- Contacts a news source.
- Calls a model.
- Changes `sources.toml`, `settings.toml` or any stored news.

## Run it

```
.\.venv\Scripts\python.exe -m steps.step01_start
.\.venv\Scripts\python.exe -m steps.step01_start --date 2026-10-06
.\.venv\Scripts\python.exe -m steps.step01_start --force
```

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step01_start`

## What it stores

- Table `runs`: date, attempt, status, start time, the settings used.
- Table `run_steps`: one row per step of a run, with its status and times.

## Good to know

- **The model key is checked only when a model is chosen.** Step 1 looks for `ANTHROPIC_API_KEY` in the environment and stops the run if it is missing. It sends nothing to the model.
- **Article text older than `article_text_days` is emptied** when a new run starts. The record that the article was read stays.
- **A held run counts as finished,** like a done one.

## Not built yet

- **The voice model check and clearing old audio.** There is no voice step yet.
- **Catching up a skipped day, and the cloud schedule.** Both come with the move to the cloud. Items up to `max_age_days` old are still picked up by the next run.
