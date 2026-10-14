# Changelog

Every commit to the project, newest first: when, which commit, which branch, and what changed.
`git log` has the full detail. Add an entry with each commit.

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
