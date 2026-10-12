# Step 3, Clean and store

Turns the raw entries from step 2 into tidy items and saves only what is new and relevant. It contacts nothing and spends nothing.

## What it does

1. Reads `runs/<date>/02_fetch/entries.json` and the settings frozen in today's run.
2. Strips HTML from titles and descriptions, and cuts descriptions to 1,500 characters.
3. Cleans each link so the same article always compares equal: no tracking codes, no `www.`, no trailing slash.
4. Drops entries older than the age limit.
5. Drops Hacker News stories and general-feed entries that match none of the AI keywords or the extra words in `also_keep`, unless they link to an article one of the AI sources published.
6. Stores new items, and refreshes points and comments on items already stored.
7. Writes a report to `runs/<date>/03_clean_store/report.md`.

## Rules

- **An item is stored once per source.** The cleaned link decides whether two entries are the same article.
- **The same article from two sources is kept twice.** That is evidence for scoring.
- **Dates come from the source and are never guessed.** An entry with no date is kept, with its date left empty.
- **The original link is kept too.** The cleaned link is only for comparing.
- **A keyword may be followed by a hyphen or a digit.** "GPT-6", "AI-generated" and "Qwen3" match; a keyword inside a longer word does not.
- **`also_keep` is read by this step only.** Step 4 treats every word of `ai_keywords` as too common to identify a story, so product names such as "opus" or "sora" go in `also_keep` and stay usable for grouping.

## It never

- Rewrites or summarises anything.
- Judges importance.
- Deletes history.

## Run it

```
.\.venv\Scripts\python.exe -m steps.step03_clean_store
.\.venv\Scripts\python.exe -m steps.step03_clean_store --date 2026-10-06
```

Step 2 must have been run for that date first.

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step03_clean_store`

## What it stores

- Table `items`: source, kind, title, link, cleaned link, description, date, points, comments, and the run that first stored it.
- Table `item_links`: the cleaned links found inside each item's description, which step 4 uses for grouping.

## Good to know

- **The AI filter is a plain keyword list.** It can miss a story worded unusually, and it can keep an unrelated story that contains a word like "model" or "cursor".
- **Widened on 9 October 2026.** Over 6 to 9 October the old filter dropped four Hacker News stories that were about AI, among them "I gave Opus 5.5 one prompt and six hours to visualize Invisible Cities" (274 points). All four are now kept.
- **The age limit counts from the moment of the fetch,** not from when this step runs.

## Not built yet

- **A model as the AI filter.** An option in the blueprint; the grouping test set decides whether the keyword list is good enough.
