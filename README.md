# AI news podcast

Once a day this collects AI news from 41 sources, groups it into stories, ranks them, writes the chosen ones from their source articles, checks every sentence against those articles, and hands over a podcast script, a newsletter and show notes for you to review. Nothing is published automatically.

## Run it

```
.\.venv\Scripts\python.exe -m steps                    # the whole day, resuming where it stopped
.\.venv\Scripts\python.exe -m steps 5                  # stop after step 5
.\.venv\Scripts\python.exe -m steps --date 2026-10-07  # another date
.\.venv\Scripts\python.exe -m steps --force            # a fresh attempt at a day already run
.\.venv\Scripts\python.exe -m steps --again 10         # repeat from step 9, 10, 11 or 12 on the script already written
```

Each step prints one line saying what it did and writes a report to `runs/<date>/<step>/report.md`. The finished package is in `out/<date>/`:

| File | What it is |
| --- | --- |
| `episode.mp3` | The spoken episode |
| `script.md` | The podcast script, checked and fitted to the length cap |
| `newsletter.md` | The same stories for reading |
| `show-notes.md` | Every story's links and confidence label |
| `review.md` | Start here: status, suggested title, what the check removed, failures, cost |
| `podcast-script.md`, `podcast-episode.mp3` | A longer, conversational episode for one presenter, from the same stories |
| `duo-script.md`, `duo-episode.mp3` | The same as a conversation between a host and a guest |

The two longer episodes are switched on and off under `[formats]` in `settings.toml`. Steps 8 to 12 each do their part for them; `steps/formats/README.md` has their rules.

## Before the first full run: choose a model

Steps 1 to 7 run without a model, but step 5 then ranks on evidence alone and cannot tell an important story from a minor one. Step 8 does the writing and cannot run without one:

1. In `settings.toml`, under `[model]`, set `provider = "anthropic"` and `name` to the model, and its prices if you want costs recorded.
2. Copy `.env.example` to `.env` and put your key in it. Git ignores `.env`, so the key is never uploaded. On a hosted run, set `ANTHROPIC_API_KEY` in the host's secret store instead.
3. Run `python -m steps`. A run that stopped at step 8 resumes there.

Without a model the run stops at step 8 and says so. Grouping (step 4) uses the model for pairs it is unsure about, and scoring (step 5) uses it as the editor that scores the stories and makes the final list.

## The steps

| Step | Folder | Does | Uses |
| --- | --- | --- | --- |
| 1 Start | `steps/step01_start` | Checks settings, connection and key; opens or resumes the day's run | Code |
| 2 Fetch | `steps/step02_fetch` | Reads every source once | Code |
| 3 Clean and store | `steps/step03_clean_store` | Tidies entries, keeps the recent and relevant ones | Code |
| 4 Group | `steps/step04_group` | Merges items about the same event into stories | Code, a free local model, the language model for unsure pairs |
| 5 Score | `steps/step05_score` | An editor scores every story by your instructions and makes the final list, with a table report | The language model, code |
| 6 Select | `steps/step06_select` | Takes the top stories of the day and reads their full articles | Code |
| 7 Plan | `steps/step07_plan` | Sets the running order and the word cap | Code |
| 8 Write | `steps/step08_write` | Writes each story from its sources only | The language model |
| 9 Check and fit | `steps/step09_check_fit` | Removes sentences whose numbers or names are not in the sources; fits to the cap; writes the final script | Code |
| 10 Voice | `steps/step10_voice` | Speaks the final script, one clip per sentence | A free voice model on this PC |
| 11 Assemble | `steps/step11_assemble` | Joins the clips into the episode; builds the newsletter and show notes | Code |
| 12 Package and log | `steps/step12_package` | Writes the review sheet and closes the run | Code |

Each step folder has its own `README.md` with its rules. `design/checklist.md` lists every rule from the design documents and where it stands.

## Where things live

- `sources.toml`: the sources and the collection filters.
- `settings.toml`: length, model, grouping thresholds, scoring weights, topics, selection limits.
- `data/local.db`: everything stored. Set `DATABASE_URL` to use PostgreSQL instead.
- `common/`: code shared by the steps; all database access is here.
- `steps/formats/`: the two longer episodes, made by steps 8 to 12 beside the regular one.
- `runs/<date>/`: each step's report. `out/<date>/`: the package.

## The daily run

A Windows scheduled task, "AI news podcast daily run", starts `run_daily.ps1` at 5:00 every morning. Each run makes the day's episode from everything collected since the last run, so the episode covers about 5:00 to 5:00.

- **The PC must be on or asleep, and plugged in.** The task wakes it from sleep; wake timers are allowed on mains power only. It cannot start a PC that is shut down.
- **A missed run starts as soon as the PC is next available,** and covers everything since the last run, up to the three-day look-back.
- **What the run printed** is kept in `runs\scheduled\<date>.log`.
- **Nothing is published.** The package waits in `out\<date>` for your review.
- **To change the time or switch it off,** open Task Scheduler and find the task by name.

Tests: `.\.venv\Scripts\python.exe -m pytest common steps`
