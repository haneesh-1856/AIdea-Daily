# Step 4, Group

Merges items about the same event into one story, in three layers from certain to uncertain.

## What it does

1. Takes every stored item that is in no story yet, and compares them with each other and with the stories of the last few days.
2. **Certain:** items with the same cleaned link are one story, and an item joins the story of an article it links to.
3. **Likely:** a free model on your machine compares the meaning of titles and descriptions. Two items alike enough are merged, if every rule below allows it.
4. **Uncertain:** pairs that are close but not merged go to the language model with one yes-or-no question: same event or not?
5. Links stories on the same subject into a thread, without merging them.
6. Makes a new story for every item that matched nothing, and writes every story and every uncertain pair to `runs/<date>/04_group/report.md`.

## Rules

- **The model judges an uncertain pair with the opening of each article,** its first 150 words, not from the headline alone. On 8 October 2026 it kept Anthropic's own post about a launch apart from the press article on it, because the post's headline did not name the product; with the openings it joins them. The pages are read here, with the same manners as step 6 (robots.txt honoured, a refusal never asked twice), and what is read is kept so that step 6 does not read it again.
- **An announcement of several things and an item about one of them are the same event.**
- **An item the writer took out of a story is never put back into it.** It is grouped afresh like a new item: it may join the story it does belong to or become one of its own. The record is in the table `splits`.

- **A shared name must be a real name.** Two items close in meaning are merged automatically only when they share a distinctive name, and a bare number, a weekday or a month is not one. On 7 October 2026 the piece "000", left over from "$1,000" and "129,000", merged a story about startup credits with one about a security programme. A pair without a shared name goes to the model to judge.

- **A story is one event: who did what, and when.** The same company or product is not enough.
- **Every item ends up in exactly one story.** No item is dropped.
- **Two stories that already exist are never merged.** A missed merge lowers a score; a wrong merge corrupts a story.
- **An automatic merge by meaning needs all of these:** alike at or above `merge_at`, different sources, no clash of version numbers, and a shared distinctive name. A name is distinctive when it is not one of the AI keywords and not in many items.
- **Anything close that fails a rule is uncertain,** and is kept apart unless the model says yes.
- **The model sees only the two items of a pair,** never the whole list, and at most `max_judge_pairs` pairs a run.
- **A digest joins nothing:** an item that links to several different stories stays its own story.
- **A source's link to its own post does not count.**
- **Old stories are closed** once their items are past `max_age_days`.
- **A new story takes its title from its most authoritative item.**
- **The reason for every match is stored:** first item, same link, one links to the other, same meaning, or the model said so.

## It never

- Drops an item.
- Lets the model rewrite or summarise anything.

## Run it

`.\.venv\Scripts\python.exe -m steps 4`, or on its own: `.\.venv\Scripts\python.exe -m steps.step04_group`

Tests: `.\.venv\Scripts\python.exe -m pytest steps/step04_group` (they use a stand-in for the local model)

## What it stores

- Table `stories`: title, thread, and the run that first saw it.
- Table `story_items`: which item is in which story, why, and the run that placed it.
- Table `threads`: stories on the same subject.
- Table `judge_log`: every uncertain pair, how alike it was, why it was uncertain, and the answer.

## Good to know

- **The thresholds are set by eye, not measured.** They come from the items of 6 and 7 October 2026. The design asks for a hand-marked test set; the uncertain-pairs table in each report is the list to mark.
- **Without a language model, uncertain pairs stay apart.** On 7 October 2026 that left two stories about OpenAI's mathematics results that should have been one.
- **The local model is downloaded once,** about 130 MB, into `data/models`.
- **Only links in the feed's short description are seen,** not links in the full article.

## Not built

- **A hand-marked test set** to tune the thresholds and measure wrong merges.
