# Step 2, Fetch

Reads every source once and brings back whatever it has. It judges nothing and spends nothing.

## What it does

1. Finds today's run, opened by step 1, and uses the settings frozen in it.
2. Requests all sources at the same time: RSS feeds, Anthropic's sitemap and the Hacker News search API.
3. Records for each source whether it worked and how many entries it gave.
4. Saves the raw entries to `runs/<date>/02_fetch/entries.json` for step 3.
5. Writes a report to `runs/<date>/02_fetch/report.md`.

## Rules

- **Only feeds, sitemaps and official APIs.** It identifies itself as a personal feed reader.
- **One fetch per run.** If step 2 is already done, nothing is requested again.
- **20 seconds per source.** A source still going after that is abandoned and counts as failed.
- **A failed source is logged and skipped.** The run continues with the others.
- **No sources at all stops the run.** If every source fails, step 2 is marked failed.
- **Entries stay raw.** HTML, tracking codes, old items and off-topic items are left for step 3.

## It never

- Logs in anywhere.
- Retries a source or works around a block.
- Cleans, filters or stores a news item.
- Calls a model.

## Run it

```
.\.venv\Scripts\python.exe -m steps.step02_fetch
.\.venv\Scripts\python.exe -m steps.step02_fetch --date 2026-10-06
```

Step 1 must have been run for that date first.

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step02_fetch`

## What it stores

- Table `source_health`: per source and run, whether it worked, how many entries, and the error if it failed.
- File `runs/<date>/02_fetch/entries.json`: the raw entries. It is not in the database and is not kept in git.

## Good to know

- **Two age limits are applied here, not in step 3.** The sitemap reader skips pages older than the age limit so it never requests them, and the Hacker News request asks only for recent stories above the minimum points.
- **The sitemap source makes more than one request.** One for the sitemap, then one for each recent page, all inside the same 20 seconds.

## Not built yet

- **Reddit and a search API.** Both are options in the blueprint, not chosen.
