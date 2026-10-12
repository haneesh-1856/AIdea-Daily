# Step 8, Write

The language model writes each story and the linking parts, from the supplied text only. This is the step that costs money.

## What it does

1. Sends one request per story: the writing rules, the story's kind and label, what was already reported, and each source's text.
2. Gets back a fixed structure: a headline, what happened, how sources see it, a brief version, and two flags.
3. Sends one last request for the opening, the watch list and the closing, from the headlines and briefs only.
4. Lays the script out one sentence per row, with a narrator's line before each story that names its sources and says its label.
5. Records the tokens and cost of every request, and writes the draft to `runs/<date>/08_write/report.md`.

## Rules

- **A source left out goes back to be grouped again,** so that what it reports is not lost. That happens in two cases: the story was written without it, or an update's sources turned out to be about something else. Step 4 of the next run groups it afresh and never returns it to the same story. A story is never emptied this way.

- **One stray source does not sink a story.** When a story's sources describe different events, the writer tells the event the title names from the sources that report it, and names the ones it left out. Those are removed from the story's sources, so they are not checked against, linked or credited. The story is set aside only when no source reports the titled event.

- **Only the supplied source text.** Nothing from the model's memory. The rules given to the model are in `prompts.py`.
- **Numbers, dates and names are copied exactly.**
- **Differences are reported only when they exist;** otherwise it says the coverage broadly agrees. Opinion is attributed by name.
- **A story whose sources describe different events is set aside.** So is an update with nothing new.
- **Each story is saved as soon as it is written.** A run that stops midway loses nothing it paid for, and a rerun asks only for what is missing.
- **A failed request sets one story aside;** the rest are written. If every story fails, the step fails.
- **The narrator's line is made by code,** so every source is always named and the label always said.
- **Each article is cut to `max_source_words`** before the model reads it.

## It never

- Runs twice for the same day.
- Adds facts, background or predictions of its own.

## Run it

`.\.venv\Scripts\python.exe -m steps 8`. It needs a model chosen under `[model]` in `settings.toml` and its key in the environment. A run started before a model was chosen picks the model up from `settings.toml` when it resumes here.

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step08_write` (they use a stand-in model and spend nothing)

## What it stores

- Table `summaries`: per story and run, the headline, what happened, how sources see it, the brief version, and any flag.
- Table `script_lines`: the script, one sentence per row.
- Table `model_calls`: every request with its tokens and cost.

## Good to know

- **Nothing here is checked yet.** Step 9 does that.
- **This step has not been run with a real model.** Only Anthropic models are wired up so far; the other models in the blueprint need their own client.
- **Hand-overs between stories are not written by the model.** The narrator's line does that job.
