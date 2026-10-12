# Step 6, Select

Chooses what makes today's episode and gathers the text to write it from. No model, no cost.

## What it does

1. Takes the editor's lineup from step 5 in order, up to `max_stories`: the final list, then the stories the recovery pass brought back, then the lighter-side stories.
2. Decides its kind from history: new, an update to a story already covered, or a correction.
3. Labels it from the kinds of source it has: confirmed, reported or rumour.
4. Picks up to five sources per story, one per outlet, primary source first.
5. Reads each source's article page and keeps the article text, without menus and adverts.
6. Writes the shortlist and what was read to `runs/<date>/06_select/report.md`.

## Rules

- **The episode is the editor's final list.** The editor decides which stories are in and in what order. `max_stories` (25) is only a safety limit for a very busy day.
- **A story under `min_score` (3) is left out even when the editor chose it,** and the report says so. Apart from the short-day rule below, nothing is added to reach a number.
- **Without a final list, the editor's action level decides.** If the request for the list failed, every story marked act now or know today that scores `min_score` or more is taken, best score first.
- **A story merged into another lends it its sources.** When the recovery pass says a story is the same event as one on the list, it is not told by itself, and the listed story is written from both sets of articles.
- **The floor is for the final list only.** A story brought in by the recovery pass or for the lighter side was chosen on its own terms.
- **The rules below still apply to a story on the list.** The editor's choice does not override them.
- **The short-day fill is now only a fallback.** The recovery pass decides what comes back. The rule below adds stories only when that pass could not be made; every story is still told one length longer on a short day.
- **A short day is filled, but never with a story marked skip.** When the editor's list makes an episode under `short_day_minutes` (15), stories the editor rated but passed over are added: first those marked know today, then those marked watch that score `watch_from` (4) or more. It stops when the episode, at the stories' usual lengths, reaches 15 minutes. Set `short_day_minutes` to 0 to leave a short day short.
- **An older story needs real new coverage to count as today's news.** If it began on an earlier day and was never in an episode, it is selected only when two or more outlets wrote about it today, or the organisation itself did. One late mention is not enough. A story first seen for the last episode is the exception: it gets this one more episode on a single mention, so that a story which arrived late or was held out is not lost between two days. When an older story is selected, the narrator says which day it first emerged.
- **Old news is left out.** A story the model marked as reporting something older than `max_age_days` is not selected.
- **Without ratings the minimum cannot apply.** If no model is chosen, the top stories by evidence are taken and the report says so.
- **Confirmed needs a primary source. Reported means press or analysts only. Anything else is a rumour,** which here means only that no feed followed wrote about it. When the model has rated it, its score decides and it is told as unconfirmed; without a rating it needs `rumour_min_points` Hacker News points.
- **A covered story with nothing new is not selected again.** With new items it comes back as an update, written from today's items only.
- **A correction to something already covered is always selected,** whatever its score.
- **robots.txt is honoured.** A site that refuses is not forced; the feed's description is used instead.
- **A page that breaks off is asked for once more.** A refusal is never asked twice.
- **A source with no text is not used, and a story with no text at all is left out.**
- **An article already read is not read again.**

## It never

- Pads the list.
- Reads paywalled or blocked pages.

## Run it

`.\.venv\Scripts\python.exe -m steps 6`

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step06_select`

## What it stores

- Table `articles`: the article text per item. Step 1 empties text older than `article_text_days`.
- Table `selections`: per run, each chosen story with its rank, score, kind, label and sources.

## Good to know

- **Whether an update has new facts is decided in step 8,** where the model compares today's sources with what was already reported.
- **A correction is recognised by words in the title,** such as "correction" or "retracts". That is crude.
- **Some sites refuse.** On 7 October 2026 openai.com answered 403, so OpenAI's own posts were written from their short descriptions.
