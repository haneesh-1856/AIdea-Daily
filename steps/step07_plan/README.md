# Step 7, Plan

Sets the order of the episode, and from each story's score how long it runs. No model, no cost.

## What it does

1. Puts each selected story in a segment: corrections, main stories or quick hits.
2. Orders the segments: headlines, corrections, main stories, quick hits, watch list.
3. Works out the word cap from `length_minutes` at `words_per_minute`: 45 minutes at 130 words a minute is 5,850 words.
4. Writes the outline to `runs/<date>/07_plan/report.md`.

## Rules

- **Corrections come right after the headlines.**
- **Updates are quick hits,** and so is any story with under 150 words of source text, however high it ranks, and any story scoring under `short_from`.
- **On a short day every story runs one length longer.** When the editor's own list makes an episode under `short_day_minutes`, a medium story becomes long, a short one medium, and a quick hit short. An update and a story with little source text stay quick hits.
- **Stories the recovery pass brought back** follow the final list: one brought back as a full segment is never shorter than a short story, and one brought back as a brief is a quick hit.
- **The lighter side has a segment of its own,** "On the lighter side", after the quick hits. Its stories run at short-story length and the narrator opens it with "And on the lighter side."
- **A story that is only worth watching goes last.** A story marked watch, added on a short day, is told as a quick hit in a "Worth watching" segment after the quick hits.
- **Each story's length is stored with the plan,** so steps 8 and 9 use the same number.
- **Length follows the score.** Under `[lengths]` in the settings: 7.5 and up is long (about 350 words), 6.5 to 7.5 medium (250), 5.5 to 6.5 short (150), and a quick hit about 70. The bars were set on 8 October 2026 for the editor's scores. A correction is never shorter than a short story. The writer in step 8 is told each story's length, and step 9 enforces it.
- **Within a segment the ranking is kept.**
- **The episode length is a ceiling, not a target.** If the day's stories pass it, step 9 shortens the lowest-ranked to their brief versions.

## It never

- Adds stories or words to fill time.
- Changes the ranking.
- Writes any of the script.

## Run it

`.\.venv\Scripts\python.exe -m steps 7`

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step07_plan`

## What it stores

- Table `episodes`: run, chosen length, word cap.
- Table `episode_stories`: the position and segment of each story.
