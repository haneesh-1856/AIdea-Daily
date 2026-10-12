# Build checklist

Every rule from `daily-run-flow.html` and `build-blueprint.html`, one line each, with where it stands.

- `[x]` built and covered by a test or a real run
- `[~]` partly built; the line says what is missing
- `[ ]` not built yet
- `[later]` outside the current target (a newsletter and a podcast script): cloud, audio, video

Target: collect, group, score, select, write and check the day's AI news, and hand over a newsletter and a podcast script.

## Whole run

- [x] 0.1 One program runs the steps in order
- [x] 0.2 A rerun skips every step already done
- [x] 0.3 Every run is logged, including failed ones
- [~] 0.4 The model is a setting, so it can be swapped without rebuilding (only Anthropic models are wired up; another maker needs its own client)
- [x] 0.5 The model key is never stored in a file
- [x] 0.6 Weights, thresholds, topic list and length live in settings, not in code
- [x] 0.7 Every model request's size and cost is recorded

## Step 1, Start

- [x] 1.1 Loads the settings and the database
- [x] 1.2 Checks the internet connection
- [x] 1.3 Checks the model key is present
- [later] 1.4 Checks the voice model
- [x] 1.5 Opens a run record that every later step attaches to
- [x] 1.6 One run per day; a second trigger does nothing unless forced
- [x] 1.7 An unfinished run resumes from its first incomplete step
- [x] 1.8 Settings are frozen for the whole run
- [x] 1.9 A broken setting stops the run before any work or spending
- [x] 1.10 A forced rerun is a new attempt; the old one is kept
- [x] 1.11 Deletes article text older than 30 days
- [x] 1.12 Deletes audio older than 14 days
- [~] 1.13 A skipped day is covered by the next run (items up to 3 days old are still picked up; no explicit catch-up)
- [later] 1.14 Starts once a day on the cloud scheduler; database loaded from a private repository
- [x] 1.15 Never contacts a news source, calls a model, or edits the source list

## Step 2, Fetch

- [x] 2.1 Reads all sources at the same time
- [x] 2.2 RSS feeds, Anthropic's sitemap and the Hacker News API
- [x] 2.3 Identifies itself as a personal feed reader
- [x] 2.4 Only feeds, sitemaps and official APIs; logs in nowhere
- [~] 2.5 One request per source per run (the sitemap source also requests each recent page, inside the same 20 seconds)
- [x] 2.6 A source that takes over 20 seconds is abandoned
- [x] 2.7 A failed source is logged and skipped; the run continues
- [x] 2.8 Never retries hard or works around a block
- [x] 2.9 Table `source_health`: per source and run, whether it worked
- [x] 2.10 A source dead for several runs is noticed

## Step 3, Clean and store

- [x] 3.1 Removes tracking codes from links and HTML from text
- [x] 3.2 Keeps title, link, date, source and short description
- [x] 3.3 Drops anything older than 3 days
- [x] 3.4 Keeps Hacker News stories only above 50 points and about AI
- [x] 3.5 Keeps general-feed entries only if they match the AI keywords
- [x] 3.6 Refreshes points and comments on items already stored
- [x] 3.7 An item is stored once per source
- [x] 3.8 The same article from two sources is kept twice
- [x] 3.9 Dates come from the source and are never guessed
- [x] 3.10 Never rewrites, judges importance or deletes history
- [x] 3.11 A Hacker News story linking to an article a source published is kept even without a keyword (added after the 6 October run lost one)

## Step 4, Group

- [x] 4.1 Certain: items that share a link, or where one links to another
- [x] 4.2 Likely: a free local model compares the meaning of titles and descriptions
- [~] 4.3 Uncertain: pairs in the middle band go to the language model with one yes-or-no question (built and tested with a stand-in; not yet run with a real model)
- [x] 4.4 Attaches new items to a story from earlier days when they match
- [x] 4.5 Links stories on the same subject into a thread, without merging them
- [x] 4.6 Records why each merge happened
- [x] 4.7 A different version number blocks an automatic merge
- [x] 4.8 A likely match must also share a distinctive name
- [x] 4.9 A match must fall within 3 days
- [x] 4.10 When unsure, keep apart; two existing stories are never merged
- [x] 4.11 The model sees only the uncertain pairs, never the whole list
- [x] 4.12 A story keeps every item and source; no item is dropped
- [x] 4.13 Every judge question and answer is logged
- [~] 4.14 Thresholds tuned on a hand-marked test set before the step is trusted (set by eye from two days of real items; no hand-marked set yet)
- [x] 4.15 Never lets the model rewrite or summarise anything

- [x] 4.16 A bare number, a weekday or a month does not count as a name two items share (fixed 9 October 2026: the piece "000" had merged two unrelated Anthropic stories)

- [x] 4.17 The model judges an uncertain pair with the opening of each article, not the headline alone (added 9 October 2026 at your request; checked on the real pair it had got wrong)
- [x] 4.18 An item the writer took out of a story is grouped afresh and never put back into that story; table `splits` (added 9 October 2026 at your request)

## Step 5, Score

Changed on 8 October 2026 at your request: an editor (the model, following your instructions in `steps/step05_score/editor.md`) now scores every story and makes the final list. Items 5.1 to 5.5 are still counted and stored, but they no longer add to a rated story's score; they only order stories with the same score and place a story that was not rated.

- [x] 5.1 Counts independent outlets; three articles from one outlet count once (changed on 7 October 2026: outlets past the third add nothing, so coverage alone cannot win)
- [x] 5.2 Credit for a primary source
- [x] 5.3 Hacker News points and comments, scaled so one huge thread does not dominate
- [x] 5.4 Credit for staying power from earlier days
- [x] 5.5 Weight for the focus areas you chose
- [x] 5.6 Tags each story with a topic from a keyword list
- [x] 5.7 Saves the score with the points from each signal
- [x] 5.8 One row per story per day, never overwritten
- [x] 5.9 Weights and topic list live in settings
- [x] 5.10 No reward for words such as "breakthrough" (the first design had no model here; changed on 7 October 2026 at your request to a model rating, and on 8 October to your editor instructions, which tell it to judge the event and not the headline; each rating is stored with its reason)
- [x] 5.11 Trending topic: a tag that keeps appearing across the past week

- [x] 5.12 Each story rated by the editor on eight questions with your weights: try today, AI impact, audience, magnitude, cost and access, novelty, credibility, future (changed on 8 October 2026 from five questions averaged equally; tried on the real news of 7 and 8 October)
- [x] 5.13 A story about something older than the look-back window is marked old news and left out (added 7 October 2026)
- [x] 5.14 An older story never in an episode is counted on today's evidence only (added 7 October 2026)
- [x] 5.15 The editor gives each story an action level (act now, know today, watch, skip) and a category (added 8 October 2026)
- [x] 5.16 The editor makes the final ranked list from the stories not marked skip, with its reason for each and the strongest stories left out (added 8 October 2026)
- [x] 5.17 The editor is told what the last three days' episodes covered, so a repeat is not told again as new (added 8 October 2026)
- [x] 5.18 A daily table report: the final list, the stories not selected, and every story scored; copied into the day's package as `scoring.md` (added 8 October 2026)
- [x] 5.20 The editor is told the window the episode covers (since the last run), and each story is marked by code as new since then or first seen earlier; "today" no longer means the calendar date (added 8 October 2026 at your request)
- [x] 5.21 Hacker News points and comments add to a rated story's score at their earlier weights, up to 1.5; a story with no thread loses nothing (restored 9 October 2026 at your request; from 8 October they had added nothing)
- [x] 5.22 Phase 2, the recovery pass: the editor looks again at every story the final list left out and decides full segment, quick brief, merged or excluded, with a reason for each (added 9 October 2026 at your request, using your `recovery.md`)
- [x] 5.23 Phase 3, the lighter side: the editor picks celebrity, viral and curiosity stories on their own terms, at most `culture_max` (3) (added 9 October 2026 at your request, using your `culture.md`)
- [x] 5.24 Importance follows the phase: the final list first in the editor's order, then recovered stories, then the lighter side (added 9 October 2026)
- [ ] 5.19 A story with no description is judged from its headline alone; reading the opening of its article first is not built

## Step 6, Select

- [x] 6.1 Takes the editor's final list in the editor's order, leaving out any story under `min_score` (3) (changed on 8 October 2026 at your request, from every story scoring 6 or more; before that, on 7 October, from the top 8)
- [x] 6.2 A limit in settings guards cost on a busy day (`max_stories`)
- [x] 6.3 A quiet day means fewer stories; never pads
- [x] 6.4 Skips a covered story when nothing new arrived
- [x] 6.5 Brings a covered story back as an update when there are new items
- [x] 6.6 A new event in the same thread is a new story
- [x] 6.7 Always selects a correction or retraction of something already reported
- [x] 6.8 Fetches the full article for up to five sources per story, primary first
- [x] 6.9 Extracts the article text without menus and adverts
- [x] 6.10 Honours robots.txt; a site that refuses is not forced
- [x] 6.11 Falls back to the feed description when a page cannot be read
- [x] 6.12 Labels each story confirmed (primary source), reported (press only) or rumour
- [x] 6.13 A rumour the model has rated is included on its score and told as unconfirmed; without a rating it needs high traction (changed on 7 October 2026 at your request, from "only with high traction")
- [x] 6.14 Table `articles`: extracted text per item
- [x] 6.15 Table `selections`: per run, each chosen story and its kind
- [x] 6.16 An older story never in an episode needs two outlets or the organisation itself writing today; the narrator says when it first emerged (added 7 October 2026)
- [x] 6.18 A story first seen for the last episode gets one more episode on a single late mention (added 8 October 2026 at your request; before that it needed two outlets or the organisation itself)
- [x] 6.19 A story the recovery pass merged into another lends that story its sources (added 9 October 2026)
- [x] 6.20 The short-day fill is a fallback for a day on which the recovery pass could not be made (changed 9 October 2026; it used to add stories whenever the list was short, which re-added ones the editor had merged)
- [x] 6.17 A short day (under 15 minutes) is filled from what the editor passed over: stories marked know today first, then stories marked watch scoring 4 or more; never a story marked skip (added 8 October 2026 at your request; this replaces "never pads" in 6.3 for those two groups only)

## Step 7, Plan

- [x] 7.1 Lays out the segments: headlines, corrections, main stories, quick hits, worth watching (short days only), watch list, closing credits
- [x] 7.2 Orders the stories by score; never changes the ranking
- [x] 7.3 Corrections come right after the headlines
- [x] 7.4 Marks updates and corrections, which are written short
- [x] 7.5 Word cap from the ceiling of 45 minutes at the voice's measured 130 words a minute (5,850)
- [x] 7.6 A story's length follows its score: long from 7.5, medium from 6.5, short from 5.5, quick hit below (changed on 7 October 2026 at your request, from "no per-story length set in advance"; the bars were 9, 8 and 7 until 8 October, when the editor's lower scores came in)
- [x] 7.7 Tables `episodes` and `episode_stories`
- [x] 7.11 "On the lighter side" is a segment of its own after the quick hits, opened by a spoken cue (added 9 October 2026)
- [x] 7.9 On a short day every story runs one length longer, and a story marked watch goes last as a quick hit in a "Worth watching" segment (added 8 October 2026 at your request)
- [x] 7.10 Each story's planned length is stored with the plan, so steps 8 and 9 use the same number (added 8 October 2026)
- [x] 7.8 No model; writes none of the script

## Step 8, Write

- [x] 8.1 One request per story: rules, source articles, label, and what was already reported
- [x] 8.2 Fixed structure back: what happened, how sources see it, a brief version, a different-events flag
- [~] 8.3 One final request writes the linking parts: opening, watch list, closing (headlines come from each story's request; hand-overs are the code-made narrator's line)
- [~] 8.4 Only the supplied source text; nothing from the model's memory (the rule is in the instructions given to the model; not yet observed with a real model)
- [~] 8.5 What happened is anchored on the primary source; numbers copied exactly (the rule is in the instructions given to the model; not yet observed with a real model)
- [~] 8.6 Differences reported only when they exist; opinion attributed by name (the rule is in the instructions given to the model; not yet observed with a real model)
- [~] 8.7 For a covered story or thread, writes only what is new (the rule is in the instructions given to the model; not yet observed with a real model; an update with nothing new is set aside)
- [x] 8.8 Each source is named and the confidence label is said
- [x] 8.9 A story whose sources describe different events is flagged and dropped
- [x] 8.10 No story runs past about four minutes
- [~] 8.11 One narrator; no invented quotes, disagreement or banter (the rule is in the instructions given to the model; not yet observed with a real model)
- [x] 8.12 Never runs twice for the same day: results are saved
- [x] 8.13 Tables `summaries` and `script_lines` (one sentence per row)
- [x] 8.14 Records tokens in and out and the cost of every request

- [x] 8.20 A story with a stray source is written from the sources that report it, and the stray one is dropped from its sources; it is set aside only when no source reports the titled event (changed 9 October 2026 at your request, from setting the whole story aside)
- [x] 8.21 A stray source goes back to be grouped again on the next run, so what it reports is not lost (added 9 October 2026 at your request)

## Step 9, Check and fit

- [x] 9.1 Compares every number, date and name in the script with the source text
- [x] 9.2 Spoken and written forms compare equal ("nine hundred million" and "$900M")
- [x] 9.3 Removes lines that do not match; never rewrites or repairs
- [x] 9.4 Checks the brief versions the same way
- [x] 9.5 A main story that loses its key facts is dropped
- [x] 9.6 Fit: full versions down the ranking until the cap, then brief versions, then nothing
- [x] 9.7 Corrections are never shortened or dropped to fit
- [x] 9.8 Under the cap the episode ends early; nothing is padded
- [x] 9.9 If more than about a fifth of the lines fail, the episode is held and you are alerted
- [x] 9.10 Table `check_log`: each removed or shortened sentence, the reason and the action
- [x] 9.11 `script_lines` marked kept or removed; `episode_stories` marked full, brief or dropped
- [x] 9.12 No model
- [x] 9.14 Only the top `headlines` stories (6) get a headline at the start of the episode (added 7 October 2026)
- [x] 9.15 The episode ends by crediting the outlets its stories came from, pointing to the show notes for links, and "Thanks for listening today."; made by code once the lineup is final; script and audio only (added 8 October 2026 at your request)
- [x] 9.13 Each story in the episode opens with a spoken cue ("Our top story today.", "Next up.", "And finally."), chosen once the lineup is final; script and audio only (added 7 October 2026)

## Step 10, Voice

- [x] 10.1 Prepares the text for speaking: figures and symbols are written the way they are said
- [x] 10.2 Speaks the script one sentence at a time and saves each clip with its length
- [~] 10.3 A free voice model (Chatterbox Turbo, chosen by ear on 7 October 2026 in place of Kokoro, which sounded too plain)
- [x] 10.4 One consistent voice: the owner's own, from a reference recording
- [x] 10.5 Nothing is sent to a paid voice service
- [x] 10.6 Preparation changes how text is spoken, never what it says
- [x] 10.7 Names the voice gets wrong are said from a list you can add to
- [x] 10.8 A failed clip is retried; if it fails again the run stops
- [x] 10.9 Never changes the words, skips a sentence silently, or adds music or effects
- [~] 10.10 Voice quality (judged by the owner on samples; nobody has yet listened to a whole episode)
- [later] 10.11 Running the voice model in the cloud: it needs a graphics card

## Step 11, Assemble

- [x] 11.1 Builds the newsletter from the same checked summaries, by template
- [x] 11.2 Builds the podcast script from the checked lines
- [x] 11.3 Builds show notes with each story's links and confidence label
- [x] 11.4 All outputs carry the same stories, in the same order
- [x] 11.5 Every story in the notes has at least one link
- [x] 11.6 Stories dropped for length appear in the notes and the newsletter
- [x] 11.7 Adds no content that is not in the verified script
- [x] 11.8 Joins the audio clips in order, with pauses, into one file; the clips are then deleted

## Step 12, Package and log

- [x] 12.1 Outputs go in a dated folder
- [x] 12.2 Review sheet: suggested title and description, the source list, everything the check removed
- [~] 12.3 Tells you the package is ready (on screen only)
- [x] 12.4 Records the stories covered, the cost and any failures; the run gets its final status
- [x] 12.5 Nothing is published or uploaded automatically
- [later] 12.6 Saves the database to the private repository; a message to your phone

## What "built" does not yet mean

- **Steps 4 (judge) and 8 have never met a real model.** No key exists on this machine. They are tested with a stand-in that returns fixed answers, so the plumbing, storage, resume and cost recording are proven; the quality of real writing is not.
- **The numbers in settings are first guesses** from two days of real news: grouping thresholds, scoring weights, the minimum score, the topic words.
- **Only Anthropic models are wired up.** The blueprint's other candidates need their own client.
