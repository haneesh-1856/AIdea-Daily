# Step 11, Assemble

Builds the newsletter and the show notes from the same checked content as the script. No model, no cost.

## What it does

1. Takes the sentences that passed step 9, in the outline's order.
2. Fills two templates and writes them to `out/<date>/`: `newsletter.md` and `show-notes.md`. The script, `script.md`, is already there: step 9 writes it the moment it is final.
3. Records step 10, voice, as passed over.

## Rules

- **All outputs carry the same stories in the same order.**
- **Nothing is added** that is not in the checked script, apart from titles, labels and links.
- **Every story in the notes has at least one link.**
- **A story left out for length still appears** in the newsletter and the notes, with its brief version if that passed the check.
- **A story dropped because it could not be trusted appears in none of them;** the review sheet explains it.
- **A held episode is marked HELD** at the top of the script and the newsletter.

## Run it

`.\.venv\Scripts\python.exe -m steps 11`

Tests: `.\.venv\Scripts\python.exe -m pytest steps/test_outputs.py`

## Not built

- **Audio.** Step 10, voice, and joining clips into an episode file are not built. The run ends with the script.
