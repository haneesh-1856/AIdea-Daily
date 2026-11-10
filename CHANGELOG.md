# Changelog

Every commit to the project, newest first: when, which commit, which branch, and what changed.
`git log` has the full detail. Add an entry with each commit.

## 2026-11-10 · `4d129e9` · `weekend-edition`

**voice-rules merged into weekend-edition: the next run (11-11, 4:00) is the first with these changes**

- Brought in, oldest first: the voice test bench and the 77 real mistakes (`c1b3320`), the fair Whisper check (`f24141b`), the podcast opening with the welcome before the hook (`b56b560`), the pronunciation lexicon and its "names not yet tested" review list (`3b9ebde`), the spelling search tool (`a3c6e60`), the first lexicon entries (`601b03e`), the C/D bench re-run (`377c9f7`), and the safe lexicon setting (`d4525d2`): only AIdea and ElevenLabs are live, and Claude, Claude Code, Anthropic and Ollama keep their old `[voice.say]` spellings.
- Merged after the 11-10 run had finished (06:52), so that run was not affected.
- To watch on 11-11: the stricter, fairer check may ask for more retakes, so the voice step may take longer.
- Tests: 419 pass; only the known step 6 test (`test_an_article_read_before_is_not_read_again`) fails.

## 2026-11-10 · `d4525d2` · `voice-rules`

**Only the bench-confirmed lexicon entries stay live (AIdea, ElevenLabs); the other names go back to their old spellings**

- Why: on the C/D bench the lexicon made names worse overall (C 4/15 to 2/15 cases passing; Claude in D03 2 to 0, Foxglove 4 to 2, Suno C06 5 to 3). Only AIdea (4 to 5) and ElevenLabs (2 to 4) clearly improved.
- `voice/lexicon.toml`: every entry except AIdea and ElevenLabs gets `status = "none"`, so it is spoken as written or by `[voice.say]`. Each entry keeps its test record, so a later bench run can turn it back on.
- `settings.toml` `[voice.say]`: restored "Claude Code" = "Clawd, Code", "Claude" = "Clawd", "Anthropic" = "Ann Thropic", "Ollama" = "Oh llama", so the episodes say these names no worse than before. "ETH" = "ether" stays dropped (the agent's reason holds).
- Kept: welcome-first, the fair judge, the lexicon mechanism and search tool, and the "names not yet tested" review list.
- `steps/step10_voice/test_step.py`: the Claude Code lexicon test is replaced by one that checks only AIdea and ElevenLabs are live and that the old spellings are used.
- Rule from now on: a spelling goes live only after a fresh bench run confirms it at 4 of 5, and as-written wins when it already scores 4 of 5.
- Tests: 418 pass, plus 174/174 in step 10 after the test change; the known step 6 test is deselected.

## 2026-11-10 · `377c9f7` · `voice-rules`

**Groups C and D re-run with the lexicon: not yet better (C 2/15, D 3/10 cases passing; before 4/15 and 2/10)**

- `experiments/voice_bench/results/cases-20261110-030349.*` (25 cases x 5 raw takes, 03:03 to 03:20) and `lexicon-before-after-C-D.md` (per case, before to after). All 25 cases were re-run; the search of the codes and abbreviations (`lexicon-terms-run4.json`) was not, because the GPU window closed.
- Better: C07 Suno 4 to 5, D07 ElevenLabs 2 to 4, D09 AIdea 4 to 5; D10 404 Media 5 to 4 (still passing). Worse or no change: Karpathy 0/5 (Whisper writes "Andresh"/"Kapati" in full sentences), Thurrock 0 to 1/5, Claude 0/5 in D03 and D04 ("Claw-d" heard "blog", "claw"), Claude Code 0/5 ("Claudine"), Foxglove 4 to 2/5 and Gizmodo 2 to 1/5 (entries that scored 5/5 in the search but not here: the search picks the best of about 9 spellings on 5 takes, so its score is optimistic; as-written had 4/5 for Foxglove and should have been kept).
- `steps/step10_voice/test_step.py`: the Claude Code test now checks the lexicon's "Claw-d Code", not a list.
- Full suite: 419 pass; the step 6 test fails as before.
- Lesson for the next step: a spelling should be confirmed on a fresh set of takes (the bench) before it counts, and as-written should be kept when it already scores 4 of 5.

## 2026-11-10 · `601b03e` · `voice-rules`

**The first tested entries in voice/lexicon.toml, and the old `[voice.say]` names moved into it**

- `voice/lexicon.toml`: 22 entries, each with its passes out of 5, the date and a real sentence. Used (4 or 5 of 5): AIdea "I-dea", Anthropic (as written, 5/5: "Ann Thropic" is no longer needed), Claude "Claw-d" (4/5; as written 1/5), ElevenLabs "Eleven Labs", Ollama "Uh-lah-muh" (4/5; "Oh llama" 2/5), Foxglove, Gizmodo "Giz-mo-dough", Huang, Karpathy, Suno, Zhang, Jalkut "Jall-cut", Rikiya "Rick-ee-ya", Takehi "Tack-eh-hee". No reliable spelling after two attempts, spoken as written and listed for escalation: Andrej, Claude Code, Claudes, Federighi, Khattab, Pierre Stock, Teoh, Thurrock.
- "Claude Code" has no entry of its own: the old "Clawd, Code" made a list ("Claude, code"; 1 of 5); "Claude Code" now becomes "Claw-d Code" through the Claude entry.
- `settings.toml` `[voice.say]`: AIdea, Claude, Claude Code, Anthropic, Ollama and ElevenLabs moved to the lexicon; "ETH" = "ether" dropped (the Exponential Time Hypothesis is in the news and would be said "ether"; no real sentence about the coin). Left in for now, not retested because the GPU window ran out: Show HN, Ep, Claudes, AWS, COBOL, tpu, robots.txt, 404 Media, WSE-3T, GR00T (`lexicon-terms-run4.json` has the next search).

## 2026-11-10 · `a3c6e60` · `voice-rules`

**The lexicon search tool: candidate spellings, voiced 5 times in real sentences, judged strictly, kept at 4 of 5**

- `experiments/voice_bench/lexicon.py`: `find` (real sentences with a name, from the bench cases, the live folder's scripts and older reports), `candidates`, `search terms.json` (two attempts per name, then "no reliable spelling" and escalation), `new <day>` (the names of that day's script not yet in the lexicon, as a terms file). Candidates: the name as written, the existing entry, a syllable split with hyphens, a phonetic respelling from espeak-ng's IPA (Huang -> Hwahng), and five respellings from the pipeline's model; the second attempt shows the model what Whisper heard for the first.
- Judging: each candidate is voiced 5 times, each in one of the real sentences (the bench's worker, retakes off), heard by Whisper, judged by `check.fault()`. A real name (Title-case words) is judged against its own spelling only, so a respelling that makes the voice say another name does not pass (the first search run accepted "Wong" for Huang because the judge also accepted the spoken form; it was stopped, its results discarded and the search run again). Abbreviations and codes (AWS, tpu, 404 Media, Ep, AIdea) may be said differently, so the spoken form counts for them. A take is right when nothing found wrong concerns the name; `clean` counts takes with nothing wrong anywhere. The best candidate with at least 4 right takes is kept, ties going to the plainest.
- `experiments/voice_bench/bench.py`: speaks with the lexicon (`--no-lexicon` for the old way). `expect` is now only asked for when `fault()` has found something (a clean verdict already proves every word and name was heard, and `expect` was stricter than the fair judge: it failed Whisper's own spelling of a name).
- `lexicon-terms*.json` are the terms searched, `results/lexicon-search*.json` hold every candidate, every take and what Whisper heard. Model cost of the searches: $0.0271 (claude-sonnet-5-5).
- Searched on 2026-11-10 from 00:27 to 03:03 on the GPU (the discarded first run, then two runs that kept their results). A run for the codes and abbreviations was cancelled when the GPU window was closing.

## 2026-11-10 · `3b9ebde` · `voice-rules`

**A tested pronunciation lexicon that `spoken()` uses, and a list of names not yet tested in each review sheet**

- `steps/step10_voice/lexicon.py` and `voice/lexicon.toml` (one table per word: `say`, `passes` out of `of`, `tested`, `sentence`; or `status = "none"` with the best spelling and score when no spelling reached 4 of 5). Only entries with a spelling and at least 4 passes are used.
- `spoken(text, say, lexicon)`: the lexicon's spellings are applied first, longest word first and in one pass (a respelling is held as a private-use character), so "Claude Code" is replaced as a whole, never as "Claude" plus "Code", and `[voice.say]` cannot respell a respelling. `[voice.say]` still works for a word with no tested entry. Step 10 and the longer episodes' voice step load the lexicon from the project folder.
- Review sheet (step 10 report): "Names not yet tested": capitalised or camel-case words that are not among the 15,000 commonest English words (`voice/common-words.txt`, from Peter Norvig's count_1w list) and not in the lexicon or `[voice.say]`. It is a list, not a GPU or model job: the daily run stays as fast as before. The search is a separate command (`experiments/voice_bench/lexicon.py`, next commit) that the owner or the post-run check runs, because it takes about 25 minutes of GPU per 6 names.
- `steps/step10_voice/test_lexicon.py`: save and load, only tested spellings used, longest-first single pass, say cannot respell a respelling, empty lexicon changes nothing, untested names and the review section, plus tests of the search tool's candidates and judge (they need the tool in the next commit).
- `steps/step10_voice/README.md` points to the lexicon.

## 2026-11-10 · `b56b560` · `voice-rules`

**The podcast always opens with the welcome, then the hook**

- Before, the plan put a `cold_open` first and "Welcome to AIdea Daily" came about 70 seconds in. Now the order is intro (the welcome and the date, about 90 words), then cold_open (the hook), then the stories, then the closing.
- `steps/formats/prompts.py`: the plan rules and the intro and cold-open rules say so; the intro's first sentence is "Welcome to {show}." and the second gives the date; the hook follows it.
- `steps/formats/write.py`, in code so that a model that ignores the prompt still gets it: `tidy_plan` always puts the intro first and the cold_open second whatever order the model gave (and adds either if missing); `ensure_welcome` makes the intro's lines start with "Welcome to <show>." and carry the date, adding a welcome line or the date when the model left them out. The kind rules are now formatted with the show's name.
- `steps/formats/test_formats.py`: the plan test orders (intro, cold_open, ...), a new test for four model orders, a new test for `ensure_welcome` (no welcome, welcome without the date, already right, empty).

## 2026-11-10 · `f24141b` · `voice-rules`

**Make the Whisper check fair: the same plain tokens on both sides, spoken form accepted, real errors still fail**

- `steps/step10_voice/check.py`: `fault(sentence, heard, spoken=None)`. A clip is fine if it says the sentence as written or as the voice was given it (`item["text"]`, which step 10 and the bench now pass), so "I-dea" / "Clawd" / "Ann Thropic" need no special case.
- Both sides are written as plain tokens (`words()`): ordinals (28th = 28), figures in words and thousands (forty-seven thousand = 47,000), trailing zeros ($5.00 = $5, 1.00000 = 1), % = percent, scale letters and words (256K = 256 thousand = 256,000; 284B = 284 billion), currency symbols and cents ($95bn = 95 billion dollars, £100m = 100 million pounds, $0.07 = 7 cents), GB = GiB = gigabytes (also MB, TB, KB), x = times, v1.1 = version 1.1, letters and digits split (64GB = 64 GB, S1A = S-1/A), contractions (you'd = you would, possessive 's dropped), U.S. = us.
- Words are compared by what is different, not by a share of words matched: joined or spaced compounds are equal (hand-written, handwritten, hand written; ProtonMail); British and American spelling by endings (our/or, ise/ize, yse/yze, tre/ter, ence/ense, elled/eled, ogue/og, dgement, scept/skept); inflections (test/tests, confirm/confirmed); homophones by espeak-ng phonemes when it is installed (weight/wait, tonnes/tons); a name (a capitalised word) may be spelt Whisper's way only if letters agree 3/4 and consonants 9/10 (Ollama/Allama, Claude/Clawed pass; Huang/Wang, Huang/Hong, Karpathy/Kaipathy, Claude/Clog fail). An ordinary word must match (boot is not boat).
- Anything else that differs is a fault: a wrong, dropped or added figure, a wrong or missing word or name, a missing clause or ending, a stutter, extra speech. Small words (a, the, to, of, is, ...) may slip once per sentence and once more for every 12 words; not, no, he/she, who/what and every figure and name may not. The "3 of 4 words heard" rule, the figure check and the ending check are gone; this does the same job and no more.
- `steps/step10_voice/test_check.py`: 41 writing-only differences that must pass, 5 spoken-form cases, 41 real errors that must fail (wrong figure, dropped figure, Wang for Huang, Kaipathy, Clog, Games for Claims, boat for boot, missing clause, who who, not dropped, he for she, ...), and the token rules.
- `experiments/voice_bench/bench.py`: judges with the spoken form too, and `--rejudge <results.json>` judges the stored Whisper text of an earlier run again without voice or GPU. Baseline re-judged: `results/cases-20261109-233815-rejudged.md`, with every changed take listed in `-flips.md` (66 fail to pass, 28 pass to fail).
- 407 tests pass; the step 6 test fails as before.

## 2026-11-10 · `c1b3320` · `voice-rules`

**Add the voice test bench and a 77-case list of real mistakes, with the "before" baseline**

- `experiments/voice_bench/bench.py`: speaks each case N times (default 5) with the real `spoken()`, `phrases()`, worker and listener, and judges each take with the real `check.fault()` plus the case's `expect`, `forbid` and `forbid_raw`. One worker job for all takes; the worker's retakes are off (`retakes = 0`), so every take is independent. A case passes with 4 of 5. `--text-only` prints text and spoken form without the GPU; `--n`, `--group`, `--ids` pick the work. It refuses to start while `python -m steps` runs or between 03:30 and 05:30.
- `experiments/voice_bench/cases.json`: 77 cases from the 10-24 to 11-09 reports and the 11-09 Whisper transcripts, in groups A numbers (16), B codes and product names (16), C names (15), D respellings (10), E short lines (12), R random slips (8).
- Baseline on unchanged code (18 min voice, 22 min with Whisper): cases passing A 0/16, B 2/16, C 3/15, D 2/10, E 2/12, R 4/8. Clips of the latest run stay in `clips/` (git-ignored); results are in `results/`.
- No change to the pipeline itself.

## 2026-11-09 · `0d58d49` · `weekend-edition`

**Give the podcast a 60-minute ceiling; the briefing keeps none**

- `settings.toml`: `max_minutes = 60` under `[formats]`. The owner's rule is now: briefing at least 15 minutes with no maximum, podcast at least 35 and at most 55 to 60.
- The podcast plan asks for at least 6,364 words (37 minutes) and never more than 10,320 (60 minutes) at 172 words a minute. Left out, `max_minutes` means no ceiling; `common/settings.py` checks it is at least `min_minutes`.
- 309 tests pass; the step 6 test fails as before.

## 2026-11-09 · `068f27c` · `weekend-edition`

**Make 15 and 35 minutes minimums with no length cap; use the measured voice paces**

- The owner's rule: the briefing runs at least 15 minutes and the podcast at least 35. On 2026-11-08 they ran 12.0 and 32.1.
- `settings.toml`: `words_per_minute` 130 → 145 and `speaking_pace` 150 → 172, measured from the runs of 2026-10-30 to 11-08 in the owner's voice. `short_day_minutes` 15 → 17 and `min_minutes` 35 → 37, a little above the minimum, since the written stories come out shorter than planned.
- `length_minutes` (45) removed. It is now optional: left out, the word cap is 0 and step 9 tells every story in full. Steps 1, 7, 9, 11 and 12 say "no length cap".
- Podcast plan (`steps/formats/prompts.py`, `write.py`): asks for at least the minimum words, with no upper limit, instead of a 35-to-40-minute range.
- 309 tests pass (2 new: no cap in step 7 and step 9). `test_an_article_read_before_is_not_read_again` in step 6 still fails, as before.

## 2026-11-08 · `f77ff5c` · `weekend-edition`

**Give the RSS.com channel link its own Listen section in the README**

- `README.md`: the link to the show on RSS.com moves from a bold line into a `## Listen` section near the top.

## 2026-11-08 · `bfae886` · `weekend-edition`

**Say "$1tn" and "$300mn" as trillion and million dollars**

- Step 10: `spoken()` reads "tn" and "mn" after a dollar amount, and in dollar ranges, the same way as "bn". On 2026-11-07, "$1tn" was said "1 dollartn" and "$2.5tn" "2.5 dollarstn".
- 307 tests pass (1 new in `steps/step10_voice/test_step.py`). One test fails, and it already failed before this change: `test_an_article_read_before_is_not_read_again` in `steps/step06_select/test_step.py`.

## 2026-11-05 · `009b0e2` · `weekend-edition`

**Leave out the duo episode; note the tiny-decimals voice problem**

- `settings.toml`: `duo = false`. Changed on 2026-11-02 and used by the daily runs from 2026-11-03 to save writing cost; committed on 2026-11-05.
- `steps/testkit.py`: the test setup now accepts `podcast` and `duo` set to either `true` or `false`, so the tests no longer break when one is switched off.
- TODO.md: new item to spell out decimals with leading zeros. On 2026-11-02, "0.00065%" was misread in 3 of 4 tries.
- Tests not run for this commit (skipped at the owner's request).

## 2026-11-02 · `8a293d8` · `weekend-edition`

**Give slow sources 40 seconds and a second try; sample a Weekend Edition**

- Step 2: `TIMEOUT` is 40 seconds instead of 20, and every source that failed is tried once more, side by side (`_read_together`). Six sources timed out on 2026-11-02 (Wired, BBC, Gizmodo, The Decoder, Tech Policy Press, Replicate).
- `experiments/weekend_edition/`: `sample.py` writes a week-in-review from the week's 5 top stories and what was reported since; `speak.py` voices it; `extra.py` writes the day's passed-over stories for the briefing and the podcast. All write from stored articles only and are fact-checked. They were used by hand to lengthen the 2026-11-02 episodes; nothing is wired into the daily run.
- TODO.md: the six quiet-day ideas, with 1 and 2 under way and 3 to 6 kept for later.
- 307 tests pass (1 new in `steps/step02_fetch/test_step.py`).
- Pull request [#2](https://github.com/haneesh-1856/AIdea-Daily/pull/2) into `main`, opened 2026-11-02, not merged yet.

## 2026-10-30 · `b0741e1` · `main`

**Say "Anthropic" as "Ann Thropic" and "Claude Code" as "Clawd, Code"**

- `"Anthropic" = "Ann Thropic"` under `[voice.say]`. The voice dropped the opening "An" ("Nthropic", "Enbropic", "Inverpick") on 2026-10-18 to 10-20, and spellings with a hyphen did no better.
- `"Claude Code" = "Clawd, Code"`, placed above `"Claude"` so it matches first. On 2026-10-29 the "d" ran into the "C" of "Code", and it was heard as "claw".
- Not sampled yet: the 2026-10-31 run is the first test. The 2026-10-30 episodes were left as they were, at the owner's request.
- 65 step 10 tests pass (1 new in `steps/step10_voice/test_step.py`).

## 2026-10-27 · `f5a4f8c` · `main`

**Merge voice-check: hear every clip back with Whisper and retake the ones that are wrong**

- Brings to `main` the check by ear (`4fb259a`), the WSE-3T pronunciation (`3c183ee`) and the 2026-10-26 pronunciation fixes (`208bc32`), with their changelog entries.
- Merged at the owner's request after the scheduled runs of 2026-10-24 to 10-26 used it; the laptop is now on `main`, so the 5:00 run uses `main`.

## 2026-10-26 · `208bc32` · `voice-check`

**Say "bn", one dollar, price lists, subreddits, Qwen versions and GR00T the way people do**

- Found by checking the 2026-10-26 episodes with Whisper: 14 sentences of the episode and 7 of the podcast were still wrong after the retakes.
- `spoken()`: "$40bn" is "40 billion dollars" (it was "40 dollarsbn"); "$1" is "1 dollar"; prices set side by side with spaced slashes, "$5 / $30 / $0.50", are said as a list with pauses (they ran together as "$5.30.50"); "r/TrueOpenSource" is "r slash True-Open-Source" (heard "Arsh, lacked true open source"); a name's version is said apart from it and from a size after it, "Qwen3.5-9B" as "Qwen 3.5, 9 billion" (heard "Qwen 3.59 billion" and "Quent 3.3.5").
- `"GR00T" = "Groot"` under `[voice.say]`: Nvidia's robot models, written with zeros, came out "gr tpus".
- The day's two episodes are kept as they were in `out/2026-10-26/original/`; re-voicing the 21 sentences was stopped when the laptop ran short of memory.
- 304 tests pass (6 new cases in `steps/step10_voice/test_step.py`).

## 2026-10-25 · `3c183ee` · `voice-check`

**Say Cerebras's WSE-3T as letters and figures, not "3 trillion"**

- `"WSE-3T" = "W S E 3 T"` under `[voice.say]`. The rule that reads 8K, 270M or 1T as numbers made it "WSE 3 trillion" in both 2026-10-25 episodes. Those two sentences were retaken and spliced in by hand that morning.

## 2026-10-24 · `4fb259a` · `voice-check`

**Hear every clip back with Whisper and retake the ones that do not say their sentence**

- New `steps/step10_voice/check.py` and `listener.py`: once the voice model has finished, Whisper (`medium.en`, on the graphics card) writes down every clip of the episode and the podcast, and each is compared with its sentence.
- A clip with 3 or more words skipped, added or changed, a phrase said twice, a lost ending, a figure not heard, or under 80% of its words heard is spoken again, up to `listen_rounds` (2) times. The take in hand is set aside as `-kept.wav`, and only the better of the two stays. Nothing here stops a run: what is still wrong is listed in step 10's report.
- New settings under `[voice]`: `listen`, `listen_model`, `listen_rounds`.
- First run, 2026-10-24: ready at 7:10. 42 clips found wrong, 28 fixed by a retake (dropped endings, garbled names and figures). Of the 14 left, 12 were Whisper writing things its own way ("£200 million" for £200m, "64 megabytes" for 64 MB) and 2 were small slips.
- On a branch until a few runs come out clean, then to be merged into `main`. 266 tests pass (12 new, in `steps/step10_voice/test_check.py`).

## 2026-10-22 · `d5de183` · `main`

**Keep the Claude Code sessions and personal settings out of git**

- The same change as `08077f3` on `video-prototype`: `.gitignore` leaves out `.claude/` and `claude-sessions/`, where a hook on this laptop copies the session transcripts.

## 2026-10-22 · `7dd9d33` · `main`

**Retake a sentence the voice cuts short, and retry a long one in phrases**

- The same change as `a049fdd` on `video-prototype`. The 2026-10-22 run stopped at step 10 on a sentence the voice cut short twice.
- The worker retakes a take quicker than 5 words a second, a little freer each time; step 10's second try speaks a long sentence in phrases.

## 2026-10-21 · `bd1e20e` · `main`

**Speak both episodes in the owner's own voice, without breaths, and retake shouted sentences**

- The same change as `3bb3252` on `video-prototype`.
- `[voice] reference` and the podcast's presenter and guest are now `voice/reference-voice2-clean.wav`: the owner reading an article, with its 26 breaths and its hiss made silent. The demo voice, of unknown origin, is no longer used. The file is not in git (`*.wav`).
- `temperature` 0.8 → 0.5: sharper. The 2026-10-21 episode matched its script 0.895 against 0.868.
- New `clean` setting: the worker silences breaths in every clip, cuts a silence inside a sentence to half a second and trims the clip's ends.
- New `retakes` and `longest_pause` settings: this voice stopped mid-sentence and came back shouting in 24 of 232 sentences, and once left out the end. A take that pauses over 2 seconds, or is 4 dB louder than the voice's usual take, is spoken again up to twice, and the calmest is kept. On 12 of the day's worst sentences every kept take was calm and whole.
- The owner tried a 10% slower pace and preferred the voice's own, so `speed` stays 1.0.
- 288 tests pass (3 new, in `steps/step10_voice/test_worker.py`).

## 2026-10-21 · `40d1fb1` · `main`

**Say the show's name, ElevenLabs, rates, tiny prices and code the way people do**

- The same change as `023cf39` on `video-prototype`, found by checking the 2026-10-20 and 2026-10-21 episodes with Whisper.
- The show's name is said "I-dea" (it was heard "80 Daily"); `[voice.say]` has ElevenLabs, COBOL, tpu, robots.txt and 404 Media; `spoken()` reads "5–6.5×", "tokens/s", "$0.0035", "GiB" and code aloud.

## 2026-10-20 · `498a94e` · `main`

**Say dates, milliseconds, AWS and Ollama the way people do**

- The same change as `420a54f` on `video-prototype`, found by checking the 2026-10-20 episodes with Whisper.
- "Oct. 20" is "October 20", "10 ms" is "10 milliseconds", "4–8x" is "4 to 8 times", a no-break hyphen is a plain one; `[voice.say]` has "AWS", "Ollama" and "Claudes".

## 2026-10-20 · `902b07b` · `main`

**Link the podcast on RSS.com from the README**

- A "Listen" line under the README's opening paragraph: https://rss.com/podcasts/aidea-daily/

## 2026-10-19 · `312adfc` · `main`

**Keep the laptop awake and its screen on during the daily run**

- The same change as `7f00f0e` on `video-prototype`. Left idle at 5:00 the laptop is throttled, and the voice step ran at 0.5 to 0.9 times real time against about 2 by hand; raising the task's priority did not help.
- `run_daily.ps1` now asks Windows to keep the system and the display on until the run ends.

## 2026-10-19 · `be449fa` · `main`

**Keep only Semafor items whose title names AI**

- The same change as `1d2e464` on `video-prototype`: a feed marked `strict = true` is matched on its title alone, and the words of `[settings] not_enough_alone` (model, agent, sonnet and others with everyday meanings) do not count on their own.
- Semafor is strict: 33 of its 191 items pass, all about AI, against 41 the ordinary way, which let in a political candidate, a stock-market wrap and a car launch.

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
