# Step 9, Check and fit

Removes anything that does not match the sources, then fits the episode to its length. No model, no cost.

## What it does

1. Pulls every number and every name out of each written sentence.
2. Looks each one up in that story's sources. A sentence with anything missing is removed.
3. Drops a story that lost its key facts.
4. Adds up the words. Over the cap, stories switch to their brief version down the ranking, then drop.
5. Puts a spoken cue before each story's title, so a listener hears where one story ends and the next begins.
6. Holds the episode if too many sentences failed.
7. Writes the final script to `out/<date>/script.md`. Nothing after this step changes a word of it.
8. Writes what was removed and why to `runs/<date>/09_check_fit/report.md`.

## Rules

- **Remove, never rewrite.** A failing sentence is taken out; nothing is repaired by guessing.
- **Written forms compare equal:** "$900M", "900 million" and "nine hundred million" are the same number.
- **A story is checked against its own sources** in full, the names of their outlets, and what earlier episodes reported about it. The opening, watch list and closing may draw on any story and on the date.
- **Brief versions are checked the same way.**
- **A story that keeps fewer than half its sentences on what happened is dropped.**
- **No story runs past its own limit,** which is 1.3 times the length its score gives it (see step 7), and never past `max_story_words`. A sentence cut for length does not count against the story's key facts.
- **Only the top `headlines` stories get a headline at the start,** so a long episode does not open with minutes of them.
- **Fitting follows the ranking:** full versions until the cap is reached, then brief versions, then nothing.
- **Corrections are never shortened or dropped to fit.**
- **Under the cap the episode simply ends early.**
- **If more than `hold_above` of the checked sentences fail, the episode is held.**
- **Cues are chosen here, not by the writer,** because only now is it known which story is first and which is last. The first is "Our top story today." (or "First up." when a correction or update leads), the last is "And finally.", and the ones between take "Next up.", "Moving on.", "In other news." and "Also today." in turn. The phrases are at the top of `step.py`. They are in the script and the audio only, not the newsletter or show notes.
- **On a short day the first story that is only worth watching is announced:** "Now, a few things worth watching.", or "And finally, one thing worth watching." when there is one.
- **The episode ends with its sources and the thanks.** After the closing sentence the narrator says "Today's stories came from ..." with each outlet once, in the order its stories were told, then "Links to every source are in the show notes." and "Thanks for listening today." A dropped story's outlets are not named, and a feed called "The Verge AI" is said as "The Verge". These lines are made by code, are not checked, and their room is kept when the episode is fitted to its cap. They are in the script and the audio only.

## It never

- Lets an unmatched figure through.
- Stretches a story to reach the cap.

## Run it

`.\.venv\Scripts\python.exe -m steps 9`

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step09_check_fit common/test_facts.py`

## What it stores

- Table `check_log`: each removed sentence, shortened story and dropped story, with the reason.
- `script_lines` marked kept, removed or unused. `episode_stories` marked full, brief or dropped.

## Good to know

- **It catches wrong facts, not wrong meaning.** "Beat" where the source says "matched" passes.
- **It is strict.** "The three founders" is removed if no source says "three", even when it is true. That is the safe direction, and the hold rule shows when it happens too often.
- **The cue, the title and the narrator's note before each story are not checked;** code makes them.
- **A removed sentence can leave a rough join** with the next one.
- **A second model pass** that asks whether each sentence is supported is the upgrade the blueprint recommends. It is not built.
