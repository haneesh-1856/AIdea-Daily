# TODO

Things to fix later. Tick them off as they are done.

## Merge the branch `voice-podcast-only-short-notes` into `main`

- [x] Run on 2026-10-15 works: `episode.mp3`, `podcast-episode.mp3`, `duo-script.md`, but no `duo-episode.mp3`, plus `show-notes-short.md` under 4,000 characters as the host counts it.
- [x] Run on 2026-10-16 works the same way.
- [x] Then merge: `git checkout main` and `git merge voice-podcast-only-short-notes`, and add the merge to `CHANGELOG.md`.
- Merged on 2026-10-16 as `2369c18`. Both runs passed; their show notes were 2,830 and 2,580 characters.

## Voice: words read wrongly (found 2026-10-14 by checking the episodes against their scripts)

- [ ] **"3M" read as "3 million".** "The jury ordered 3M to pay $61.5m" was said as "3 million to pay...".
  The `\d+[KMBT]` rule in `spoken()` (`steps/step10_voice/step.py`) turns the company name into a number.
  Simplest fix: add `"3M" = "three M"` under `[voice.say]` in `settings.toml`.
  The `$` rule no longer turns "$3M" into "$three M" when that entry is added, but "3M tokens" would then be
  said "three M tokens", so it is still open.
- [x] **Comma swallowed after a dollar amount.** "Premium at $30, Super at $100" was said as
  "30, dollars Super". The `$` rule in `spoken()` matches `[\d,]*`, so it takes the comma with the number.
- [x] **Dollar ranges.** "$8-9 million" is said as "8 dollars-9 million". It should be "8 to 9 million dollars".
- [x] **Sentence split after month abbreviations.** "Friday, Oct. 16" is split at "Oct.", so "16." is
  spoken as its own sentence after a pause. The splitter should not end a sentence after Jan., Feb., ... Dec.
- [x] Add tests for the three fixed ones in `steps/step10_voice/test_step.py` and `common/test_facts.py`.

## Voice: words read wrongly (found 2026-10-17, fixed the same day)

- [x] "Claude" said as "Clod" or "Clog": `"Claude" = "Clawd"` under `[voice.say]`.
- [x] Prices with cents garbled ("$2,599.99" came out as "2,599 tense palettes"): now "2,599 dollars and 99 cents"; "$504.00 USD" is "504 dollars".
- [x] Model and port numbers garbled ("Flash 1017" said three different ways): a four-figure number that is not a year is said in pairs, "10 17".
- [x] "Coverage broadly agrees." was said after 15 to 18 stories a day, also after single-source and unconfirmed ones. It is no longer put in the script.
- [x] The same release picked twice (Beam on Hugging Face and Beam on Ollama): the final-list request now says to select only one.
- [ ] Listen to the next episode for "Clawd", the cents and the paired numbers, since the voice model can still surprise.

## Voice: automatic check after each run (idea)

- [ ] Add a step after voicing that transcribes each episode with the local Whisper model
  (`faster-whisper small.en`, already in `.venv-voice`) and compares it with the script. It should flag
  skipped, repeated or extra words, long silences, and sentences spoken too fast or too slow.
  Notes from the manual check on 2026-10-14:
  - Load `import torch` before `faster_whisper`, or CUDA fails with "cublas64_12.dll not found".
  - On long files Whisper drops some lines. Before reporting a skip, re-transcribe the window on its own
    and check whether there is sound there.
  - Whisper writes numbers and names its own way ("Allama" for Ollama, "$61 .5 million"), so ignore differences of a word or two.
  - Measure pace from the waveform, not from Whisper's word times: Whisper often stretches the first word over the pause before it.

## Other

- [ ] The voice report shows "2–3%" as garbled characters (`2â€“3`): an encoding problem somewhere between the script and the report.
- [ ] Keep the laptop plugged in from 5:00 to about 7:30. The three episodes take over 2 hours to voice, and on 2026-10-14 the battery died at about 7:35.
