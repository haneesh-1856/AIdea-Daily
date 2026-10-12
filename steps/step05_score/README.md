# Step 5, Score

An editor judges the day's stories and makes the final list. The editor is the language model, following your instructions in `editor.md`.

## What it does

1. Takes every story that gained an item today.
2. Reads the opening of the article for each story whose description has fewer than 15 words, so the editor has something to judge it by.
3. Sends the editor your instructions with the stories, 15 to a request. For each story the editor gives eight ratings from 0 to 10, an action level (act now, know today, watch or skip), a category, and one sentence on what happened. It also says whether the story is old news.
4. Works out each story's score: the weighted average of the eight ratings, using the weights under `[score.rubric]`.
5. Puts the stories not marked skip before the editor once more, best score first, up to 45. The editor returns the final ranked list, with its reasons, and the strongest stories it left out.
6. **Phase 2, the recovery pass.** Sends the editor your `recovery.md` with every story the final list left out, skipped ones included. For each it decides: a full segment, a quick brief, merged into a story on the list, or excluded, with a one-line reason every time.
7. **Phase 3, the lighter side.** Sends the editor your `culture.md` with everything still out, and asks for the celebrity, viral and curiosity stories worth a place, at most `culture_max` (3).
8. Counts the evidence for each story (outlets, a primary source, Hacker News, earlier days), gives it a topic, and stores everything.
9. Writes the report to `runs/<date>/05_score/report.md`: the final list, the stories not selected, and a table of every story scored. Step 12 copies it into the day's package as `scoring.md`.

## Rules

- **The instructions are yours.** `editor.md` is sent whole with every request. Change the text there to change how stories are judged.
- **The score is the editor's, plus Hacker News points and comments.** They count as they did before the editor was brought in (about 0.6 at 100 points, 0.9 at 1,000, plus a little for comments), up to `traction_max` (1.5). A story with no Hacker News thread loses nothing: it keeps the editor's score, and no rule leaves it out for lacking points. How many outlets covered a story adds nothing.
- **The extra is added by code, after the editor has judged.** The editor itself still does not see the points.
- **The editor sees who reported a story, not how popular it is.** Sources are shown so it can judge how well supported a story is. Hacker News points and comments are not shown.
- **Importance follows the phase.** The final list is phase 1 and keeps the editor's order. Phase 2's stories come after it, full segments before briefs. Phase 3's come last. A later phase can add to the episode; it can never reorder or remove what an earlier one chose.
- **Each later pass gets the main instructions with its own section added,** so it judges by the same standards as the first.
- **Every story left out has a reason,** from the recovery pass, which looks at all of them.
- **The lighter side is judged on its own terms.** Its stories usually score low on the eight questions, so the floor `min_score` does not apply to them.
- **The final list decides the episode's core.** Step 6 takes those stories in the editor's order. The editor may place a lower score above a higher one.
- **"Today" means since the last episode, not the calendar date.** The pipeline takes in everything it has not seen before, so an episode covers the time from the last run to this one. The editor is told when the last episode was made, and each story is marked by code as new since then, or as first seen earlier and told or not yet told. A morning run therefore does not find yesterday evening's news old.
- **The editor is told what the last three days' episodes covered,** and to select one of those again only when today's item adds something new.
- **A returning story shows what is new.** A story that began on an earlier day lists the headlines collected since the last episode on a line of their own, with their own description beneath, apart from the story's older headlines and description. Its own title stays on the first line, because a rating is matched to its story by that title.
- **The opening is read only to judge by.** It is the first 150 words of the story's most authoritative article, read with the same reader as step 6, which asks each site's robots.txt first. The page is stored, so step 6 does not read it again.
- **Evidence only breaks ties.** Stories with the same score are put before the editor in the order of their evidence.
- **Every rating is stored with its reason,** so you can see why a story ranked where it did.
- **An older story never in an episode is counted on today's evidence only.**
- **Scores are never overwritten.** One row per story per run.

## When something fails

- **An article's opening cannot be read:** that story is rated from its headline, as before.
- **A rating request fails:** those stories are not rated, and the report says how many.
- **The recovery pass or the lighter-side pass fails:** the final list stands, the report says which pass failed, and the short-day rule in step 6 does the filling instead.
- **The final list cannot be made:** the scores stand, the report says so, and step 6 takes the stories marked act now or know today instead.
- **No model is chosen:** nothing is rated, and the ranking rests on the evidence alone. The report says so at the top.

## Run it

`.\.venv\Scripts\python.exe -m steps 5`, or on its own: `.\.venv\Scripts\python.exe -m steps.step05_score`

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step05_score` (they use a stand-in model)

## What it stores

- Table `scores`: story, run, score, topic, the eight ratings with the action level and reason, the place on the final list with the editor's explanation, and what was counted as evidence.
- Table `model_calls`: each request with its tokens and cost, marked `rate`, `edit`, `recover` or `culture`.

## Good to know

- **Adopted on 8 October 2026 at your request,** replacing five questions averaged equally plus up to 3.5 points for coverage. Under the old scoring, coverage reordered the list as much as importance did.
- **Tried first on real news.** The 113 stories of 7 October cost 31 cents and gave a final list of 11; the 28 stories of 8 October cost 11 cents and gave 7.
- **The scores run lower than the old ones.** The length tiers under `[lengths]` and the floor `min_score` were moved down to match.
- **The editor's reasons can be wrong.** On 8 October it called a story "primary-source" when the only source was The Verge. The reasons are not fact-checked; the script still is, in step 9.
- **A story with no description used to be judged from its headline.** On 7 October that was 36 of 113 stories, mostly Hacker News posts, and on 9 October a new DeepSeek model was scored low as "too vague to judge". Since 9 October the editor is shown the opening of the article instead. A story whose page cannot be read is still judged from its headline.
- **When the editor merges two stories into one entry,** only the story it names is selected; the other is left out.
- **The instructions' sections 13 and 14 describe a written layout.** The answer comes back as data instead, and the report lays it out.
- **Topics come from a keyword list, which is crude.**
