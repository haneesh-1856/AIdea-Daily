# Changelog

Every commit to the project, newest first: when, which commit, which branch, and what changed.
`git log` has the full detail. Add an entry with each commit.

## 2026-10-20 · `420a54f` · branch `video-prototype`

**Say dates, milliseconds, AWS and Ollama the way people do**

- Found by checking the 2026-10-20 episodes against their scripts with Whisper. Each rule is for a mistake made more than once, that day or across days.
- "Oct. 20, 2026" is "October 20, 2026" (said "AUC 202026"), "10 ms" is "10 milliseconds" (said "mesemes"), "4–8x" is "4 to 8 times", and a no-break hyphen is a plain one ("low-resource" was said "low-free source").
- `[voice.say]`: "AWS" is "A-W-S", "Ollama" is "Oh llama", "Claudes" is "Clawds". The spellings were picked by speaking each candidate five times and transcribing it: "A-W-S" was right 5 times out of 5 against about half for "AWS".
- No spelling of "Anthropic" or "Claude" did reliably better than the current one, so they are left as they are.
- 280 tests pass (3 new).

## 2026-10-19 · `7f00f0e` · branch `video-prototype`

**Keep the laptop awake and its screen on during the daily run**

- The voice step ran at 0.5 to 0.9 times real time on the 5:00 runs of 13 to 19 October. Re-speaking 18 October's script by hand took 21.0 minutes against 53.4 at 5:00 (1.9 to 2.0 times real time).
- Raising the scheduled task's priority from 7 to 4 did not help: on 19 October the episode still ran at 0.78 times real time. The laptop being left idle is the cause. Unplugged at 5:57, it also went into standby, which froze the run until 6:24.
- `run_daily.ps1` now asks Windows to keep the system and the display on until the run ends (`SetThreadExecutionState`), then releases the request. Closing the lid still puts the laptop to sleep.

## 2026-10-19 · `1d2e464` · branch `video-prototype`

**Keep only Semafor items whose title names AI**

- Semafor's feed covers politics, war and business, and its summaries mention AI in passing: the ordinary filter let in a political candidate, a stock-market wrap, data-center financing and "Tesla and Porsche unveil new models".
- New feed option `strict = true` (general feeds only): the title alone is matched, and the words of the new `[settings] not_enough_alone` list (model, agent, transformer, sonnet, cursor and others with everyday meanings) do not count on their own.
- Semafor is strict. Of its 191 items, 41 matched the ordinary way and 33 match strictly, all about AI; the one AI story lost was "OpenRouter challenger closes seed round".
- The step 3 report's "Off topic" line explains the strict rule. 277 tests pass (2 new).

## 2026-10-19 · `54aef45` · branch `video-prototype`

**Add Semafor as a source**

- `https://www.semafor.com/rss.xml`, press, general: one feed for all of Semafor, so only items matching the AI keywords are kept (10 of 46 over the three days to 19 October).
- robots.txt allows the article pages; step 6 reads them in full (short briefs of about 120 words).
- 44 feeds now. Two run tests count the real sources, so they expect 45 of 45 (with Hacker News) and 80 entries.
- 275 tests pass.

## 2026-10-18 · `38247a6` · branch `video-prototype`

**Say cents, comma numbers and long model names the way people do**

- Found by checking the 2026-10-18 episodes against their scripts with Whisper.
- "$0.20" is "20 cents"; "dollar" only before a noun ("the 36,864 dollar bounty", but "the 2,399 dollars is").
- A number with a comma is given to the voice in words: "2,399" was said "2,039" four times out of four.
- "Deepseek-V4.1-Flash-1017" is said in parts; "Show HN", "Ep" and "ETH" have `[voice.say]` entries; a headline's "|" is a pause.
- 275 tests pass.

## 2026-10-17 · `1028cd7` · branch `video-prototype`

**Add the video prototype: an edited 1080p video from each day's episode**

- A Remotion project in `video/`; `video/README.md` gives the commands in order.
- Every shot starts where Whisper hears its first word, so the picture cannot fall behind the voice. Timing from the stored clip lengths had drifted almost 3 seconds by the end of 2026-10-16.
- A music bed synthesised in code, about 20 dB under the voice.
- Each story's lead image, skipping text cards and logos, plus two SDXL-Turbo illustrations per story, all with slow pan and zoom.
- Number callouts leave out model names, versions and codes ("Flash 1017", "firmware 13.60", "port 8081").
- Made for 2026-10-16 and 2026-10-17: `out/<day>/episode-video*.mp4`, not in git.

## 2026-10-17 · `b9d0622` · branch `video-prototype`

**Fix voice misreadings and drop the repeated "Coverage broadly agrees."**

- Found by checking the 2026-10-17 episode against its script with Whisper.
- "Claude" is said "Clawd" (`[voice.say]`). Prices with cents are said with cents, and ".00" and a trailing "USD" are dropped. Four-figure codes are said in pairs ("10 17").
- From `TODO.md`: the comma after a dollar amount stays a comma, ranges are "8 to 9 million dollars", and "Oct." no longer ends a sentence.
- "Coverage broadly agrees." is left out of the script. It had followed 15 to 18 stories a day, including single-source ones.
- The final-list request tells the editor to select only one post per release: Beam was picked twice on 2026-10-17.
- 269 tests pass.

## 2026-10-16 · `2369c18` · `main`

**Merge `voice-podcast-only-short-notes` into `main`**

- Brings the `speak` setting, `show-notes-short.md`, `TODO.md` and this changelog to `main`.
- Both test runs passed: 2026-10-15 and 2026-10-16 each made `episode.mp3`, `podcast-episode.mp3` and `duo-script.md`, no `duo-episode.mp3`, and short show notes of 2,830 and 2,580 characters.
- `TODO.md`: the merge items are ticked off.

## 2026-10-15 · `220a54f` · `main`, and `fe6a4e0` · branch `voice-podcast-only-short-notes`

**Say the show's name as "Aidea", not "AI-dea"**

- A `[voice.say]` entry in `settings.toml`. The voice had split AIdea at the capital, as it does OpenAI.
- Committed to `main` and brought onto the branch, so the 2026-10-15 test run already uses it.

## 2026-10-14 · `2c6c9a7` · branch `voice-podcast-only-short-notes`

**Add the plan to merge into main after two good runs to TODO.md**

- The branch merges into `main` once the 2026-10-15 and 2026-10-16 runs work.

## 2026-10-14 · `51bf653` · branch `voice-podcast-only-short-notes`

**Add a changelog of every commit**

- This file.

## 2026-10-14 · `e41304d` · branch `voice-podcast-only-short-notes`

**Voice only the podcast, add short show notes, add a TODO list**

- New `speak` setting under `[formats]`: step 10 voices only the formats listed. The two-person podcast keeps its script but gets no audio for now.
- Step 11 also writes `show-notes-short.md`: plain text under the podcast host's 4,000-character limit, counted the way the host counts it.
- `TODO.md` lists voice misreadings found by checking today's audio against the scripts.

## 2026-10-13 · `298dcd6` · `main`

**Add a run lock, spoken source credits and Vals AI sources**

- Only one run works at a time. The scheduled 5:00 run and a manual run had written podcast clips to the same folder.
- The longer episodes end with a spoken line, made by code, crediting the day's sources.
- Three Vals AI sources, through a new listing source type for pages that carry their own list.

## 2026-10-12 · `14fb08c` · `main`

**Add two longer episode formats: podcast and two-person podcast**

- Each run hands over three scripts and three episodes: the regular briefing, a one-presenter podcast and a host-and-guest podcast.
- Steps 8 to 12 plan, write, check, voice, join and list the longer formats. A format that fails is left out without affecting the regular episode.

## 2026-10-12 · `5f214f5` · `main`

**Add the AIdea Daily pipeline**

- The twelve-step daily run from feeds to finished audio, with its settings, source list, design notes and branding.
