# Changelog

Every commit to the project, newest first: when, which commit, which branch, and what changed.
`git log` has the full detail. Add an entry with each commit.

## 2026-10-19 · `e3eca94`, `8623661` · `main`

**Add Semafor as a source, and count it in the README**

- `https://www.semafor.com/rss.xml`, press, general: only items matching the AI keywords are kept (10 of 46 over the three days to 19 October). robots.txt allows the article pages.
- The same change as `54aef45` on `video-prototype`; the two run tests that count the real sources now expect 45 of 45 and 80 entries.
- README: 44 sources.

## 2026-10-18 · `fd93ee9` · `main`

**Open the README with what the pipeline does and what is measured**

- A short overview for readers new to the project: inputs, outputs, models, cost per day, tests, the six stages, and the parts worth reading.
- The operator's manual follows unchanged, except the source count (43, not 41).

## 2026-10-18 · `6e82b41` · `main`, from `38247a6` · branch `video-prototype`

**Say cents, comma numbers and long model names the way people do**

- "$0.20" is "20 cents"; "dollar" only before a noun; a number with a comma is given to the voice in words ("2,399" was said "2,039").
- Hyphen-joined model names are said in parts; `[voice.say]` entries for "Show HN", "Ep" and "ETH". 275 tests pass.

## 2026-10-17 · `39784cf` · `main`, from `b9d0622` · branch `video-prototype`

**Fix voice misreadings and drop the repeated "Coverage broadly agrees."**

- Found by checking the 2026-10-17 episode against its script with Whisper.
- "Claude" is said "Clawd" (`[voice.say]`). Prices with cents are said with cents, and ".00" and a trailing "USD" are dropped. Four-figure codes are said in pairs ("10 17").
- From `TODO.md`: the comma after a dollar amount stays a comma, ranges are "8 to 9 million dollars", and "Oct." no longer ends a sentence.
- "Coverage broadly agrees." is left out of the script. It had followed 15 to 18 stories a day, including single-source ones.
- The final-list request tells the editor to select only one post per release: Beam was picked twice on 2026-10-17.
- Brought onto `main` on its own; the video prototype stays on its branch. 269 tests pass on `main`.

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
