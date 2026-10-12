# The longer episodes

Besides the regular briefing, a run makes two longer episodes from the same stories and the same source articles:

| Format | Who speaks | Script | Audio |
| --- | --- | --- | --- |
| Podcast | One presenter, conversational | `podcast-script.md` | `podcast-episode.mp3` |
| Two-person podcast | A host and a guest | `duo-script.md` | `duo-episode.mp3` |

They are not steps of their own. Each of steps 8 to 12 does its part for them after its work on the regular episode:

| Step | File here | Does |
| --- | --- | --- |
| 8 Write | `write.py`, `prompts.py` | Plans the segments once for both formats, then writes each format one segment at a time |
| 9 Check and fit | `check.py` | Compares every sentence with the sources and writes the script pages |
| 10 Voice | `voice.py` | Speaks each script, every speaker in their own reference voice |
| 11 Assemble | `voice.py` | Joins the clips into the episode files |
| 12 Package | (in step 12) | Lists them on the review sheet |

## Rules

- **Same stories, same order.** One plan serves both formats. Every story the regular script wrote is told exactly once; a story the plan forgets is added to a catch-up segment by code.
- **Facts only from the sources.** The writer gets each story's stored articles, as in step 8. It may add interpretation and everyday examples, and must list each example it made up; the script page prints that list.
- **The check flags, it does not remove.** A conversation cannot lose a sentence without breaking. A sentence with a figure or a name not found in its segment's sources is kept and listed at the end of the script and on the review sheet. The first word of a sentence and whole numbers up to 12 are not checked, because talk is full of both.
- **A failure never stops the regular episode.** A format the model or the voice fails on is left out for the day, and the review sheet says why.
- **Nothing is paid for twice.** Each segment is saved when written and each clip when spoken, so a run that stops resumes with only what is missing. `--again 10` speaks only the pieces that have no clip.
- **Length.** The plan aims for `min_minutes` at `speaking_pace`. If the day's news cannot carry that without padding, the plan is shorter and says so.

## Settings

Under `[formats]` in `settings.toml`: switch each format on or off, the show's name, the length to aim for, the reference voice of each speaker, and the pauses. A run started before a format was switched on does not make it.

Use only voices you have the right to use. `voice/two_voice_test.py` is the earlier hand-run test and is not part of the run.
