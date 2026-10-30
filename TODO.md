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
  Checked with Whisper on 2026-10-18: the paired numbers work ("Flash 10 17"), the cents are said, and "Coverage
  broadly agrees." is gone. "Clawd" is mixed: Whisper heard "Claude" or "Claud" five times, "Clod" four times and
  "Clawed" once, so it needs a listen by ear.

## Voice: words read wrongly (found 2026-10-18, fixed the same day)

- [x] "$0.20" said "0 dollars and 20 cents": now "20 cents".
- [x] "The $2,399 is" said "The 2,399 dollar is", and "the 85 to $95,000 range" said "95,000 dollars range": "dollar" is used only before a noun.
- [x] "$2,399" said "2,039" or "2,099", four times out of four: a number with a comma is now given to the voice in words.
- [x] "Deepseek-V4.1-Flash-1017" said "version 4.1.1 10 17": a name strung together with hyphens and digits is said in parts.
- [x] "Show HN" said "Shoei Gen", "Ep 6" said "Ep 6th", "ETH" said "8H": `[voice.say]` entries. A headline's "|" is now a pause.
- [ ] Once each, not fixed: "First up." heard as "First step.", "Lebanon" as "Mubenon", "what's new?" as "whunge new",
  "The Decoder" as "The Dakota", "Masad" as "Masaag". The voice model slips like this now and then; listen for them again.

## Voice: words read wrongly (found 2026-10-19 and 2026-10-20)

- [x] "Oct. 20, 2026" said "AUC 202026", "10 ms" said "10 mesemes" (twice), "4–8x" said "4x 8x", and "low‑resource" (a no-break hyphen) said "low-free source": rules in `spoken()`.
- [x] "AWS" said "Ossebusian" and "Allsagas", "Ollama" said "Alama" or "Olima" five times, "Claudes" said "clods" three times: `[voice.say]` entries, picked by speaking each spelling five times.
- [ ] **"Anthropic" slurred** on 2026-10-18, 10-19 and 10-20 ("Inverpick", "and through PIC", "Enbropic", "Nthropic"), mostly right but not always. No respelling tried ("An-thropic", "Ann-thropic", "Ann-throppick", "Ann-throw-pick") did reliably better.
  2026-10-30: now `"Anthropic" = "Ann Thropic"` (a space, not a hyphen). Check it in the 2026-10-31 episodes.
- [ ] **"Claude" in "Claude Code"** heard "clod code" nearly every time, in every spelling tried ("Clawd", "Klawd", "Clawed", "Claw-d", "Clawwd"). Before "Haiku" it is heard "Claude" 4 times out of 6. Whisper predates Claude and "clawed" sounds like "clod" in many American accents, so it needs a listen by ear.
  2026-10-30: now `"Claude Code" = "Clawd, Code"`. On 10-29 it was heard "claw" because the "d" ran into the "C" of "Code". Check it in the 2026-10-31 episodes.
- [ ] Once each, not fixed by a rule: "20.59 percent" said "20.9", "123 million" said "1233 million", "runs 115." said "11.5 teen", "Qwen3.8" said "Qwen 3.1… 3.8", "deleting an account" said "the leading-in account", "EN 18286:2026" garbled (2026-10-19). The automatic check below would catch and re-speak these.
- [x] The show's name heard "Adia Daily" (2026-10-20) and "80 Daily" (2026-10-21): `"AIdea" = "I-dea"`, heard "Idea Daily" 5 times out of 5.

## Voice: words read wrongly (found 2026-10-21, fixed the same day)

- [x] "ElevenLabs" said "11 Ls" or "11 Mobs" five times, "COBOL" said "seal-ball", "tpu" said "tupu" three times, "robots.txt" said "robots docs", "404 Media" said "four honed Media": `[voice.say]` entries, picked by speaking each spelling five times.
- [x] "5–6.5×" said "5 6.5 times", "tokens/s" said "token slash S", "$0.0035/min" heard "$0.35", "8 GiB" given as "8 Gi B", and code ("device_map", "pipe.to", "torch_xla", "F.scaled_mm") garbled: rules in `spoken()`.
- [ ] Once each, not fixed: "211" said "two eleven", "318,484" heard "3018,484", "to have itself" said "have itself", "Qwen3" heard "Qwen free". "Claude" in the podcast heard "Clod" four times in a row at 43:51 to 44:43.

## Voice: the owner's own voice (from 2026-10-22)

- [ ] Listen to the 2026-10-22 episodes, the first in the owner's voice: breaths, shouting after a pause, and sentences cut short.
  Retakes catch long pauses and loud takes, but not every dropped ending; the check below would.
- [ ] It adds about 10 to 15% to the voice step's time (about 1 sentence in 10 is spoken again).
- [ ] Re-record the reference somewhere quiet if breaths still come through: only its first 10 seconds or so shape the voice.

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
