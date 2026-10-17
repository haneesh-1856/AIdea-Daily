"""Step 5, Score: an editor's judgement of each story, and from it the day's final list."""

import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError

from common import articles, db, model, runlog, scores, selections
from common.report import step_folder, write_report
from common.settings import ROOT, database_url
from common.text import phrase_pattern

STEP = 5
MAX_STAYING_DAYS = 3
MAX_OUTLETS = 3  # outlets past the third add nothing: more coverage is more confidence, not more importance
BATCH = 15  # stories rated in one request
MAX_CANDIDATES = 45  # the most stories put before the editor for the final list
Read = Callable[[str], tuple[str, str | None]]  # an article's address -> (status, its text)
THIN_DESCRIPTION_WORDS = 15  # with fewer words than this to go on, the editor is shown the opening of the article
OPENING_WORDS = 150  # how much of an article the editor is shown
KIND_ORDER = {"primary": 0, "press": 1, "newsletter": 2, "traction": 3}  # whose article is read, most authoritative first
# The editor's instructions, as the owner wrote them. They are sent whole with every request.
EDITOR = Path(__file__).with_name("editor.md")
# Two additions to those instructions, also the owner's, each used for a pass of its own after the final list is made.
# Phase 1 is the list itself. Phase 2 looks again at everything left out, so that a worthwhile story is not lost.
# Phase 3 looks for celebrity, viral and curiosity stories. A story's importance follows its phase: 1, then 2, then 3.
RECOVERY = Path(__file__).with_name("recovery.md")
CULTURE = Path(__file__).with_name("culture.md")
DECISIONS = ("full", "brief", "merge", "exclude")
# The eight questions of the instructions' section 5, with the weights given there. settings.toml can change them.
RUBRIC = {
    "immediate_value": 25, "ai_impact": 20, "audience_relevance": 15, "magnitude": 10, "practical_impact": 10,
    "novelty": 5, "credibility": 5, "future_significance": 10,
}
ASKED = {
    "immediate_value": "Try today", "ai_impact": "AI impact", "audience_relevance": "Audience", "magnitude": "Magnitude",
    "practical_impact": "Cost and access", "novelty": "Novelty", "credibility": "Credibility", "future_significance": "Future",
}
ACTIONS = {"ACT NOW": "🔥 Act now", "KNOW TODAY": "👀 Know today", "WATCH": "📌 Watch", "SKIP": "❌ Skip"}
CATEGORIES = ("Model", "Product", "Policy", "Pricing", "Program", "Business", "Infrastructure", "Research", "Other")
POINTS = ("importance", "outlet", "primary", "hn_points", "hn_comments", "staying", "focus")

RATE_TASK = """\
Stories to rate. Date: {day}

{window} "Today" in your instructions means this window, not the calendar date: a candidate marked "new since the \
last episode" is new today even when it was published yesterday, and one "not yet told in an episode" is still new \
to the listener.

This request is sections 5 and 6 only. Score every candidate below on the eight dimensions, 0 to 10 each, and give \
its action level and category. The final ranked list is made in a later request, so do not rank here.

For each candidate also give:
- story and headline: its number, and its headline copied exactly as given here.
- reason: what actually happened, in one sentence of at most 25 words.
- new_today: false only when it merely reports something that happened before the last episode, or was already \
told in one and nothing has happened since.
- stale: true when it is about something that happened more than {days} days before the date above and nothing \
new has happened since.

Rate only from what is given here. If a candidate is too vague to judge, score it low and say so. Return one entry \
for every candidate."""

EDIT_TASK = """\
Scored candidates. Date: {day}

Every candidate has now been scored (sections 5 and 6). Below are the candidates that were not marked SKIP, best \
score first, each with its weighted score and action level. Now do sections 7 to 16: deduplicate, apply the \
Immediate Action boost, use editorial judgment, and produce the final ranked list and the 3 to 5 strongest stories \
that were not selected. Refer to each story by its number, and give its title copied exactly as given here.
Never select two candidates about the same release, such as a model's launch post and a partner's post that it is \
available there: they are one event, so select only the fuller one."""

RECENT_NOTE = (
    "Already told in the episodes of the last few days. Select one of these again only when today's candidate adds "
    "something materially new:"
)

RECOVER_TASK = """\
Recovery pass. Date: {day}

{window}

The final ranked list has been made: it is under "Selected" below. Now do the missed-story recovery pass on every \
candidate under "Remaining". For each one decide:
- full: it deserves a full segment in the episode.
- brief: it deserves a quick brief.
- merge: it is the same event as one of the selected stories, or belongs inside it. Give that story's number from \
the Selected list in merge_into.
- exclude: it stays out. Give the specific reason.

Give one line of reason for every decision, and give merge_into as 0 unless the decision is merge. Return one entry \
for every remaining candidate. Refer to each by its number, and give its title copied exactly as given here."""

CULTURE_TASK = """\
Lighter side pass. Date: {day}

{window}

The lineup so far is under "In the episode" below. Now apply the additional editorial category to the candidates \
under "Remaining": choose the celebrity, viral, curiosity and human-interest stories that deserve a place for \
variety, at most {most}. Choose none when none is good enough: the AI connection must be meaningful and the story \
credible. For each one chosen give interest, 0 to 10, from the considerations in that section, and one line on why \
it is worth telling. Refer to each by its number, and give its title copied exactly as given here."""

RECOVER_ANSWER = {
    "type": "object",
    "properties": {"decisions": {"type": "array", "items": {
        "type": "object",
        "properties": {"story": {"type": "integer"}, "title": {"type": "string"}, "decision": {"type": "string", "enum": list(DECISIONS)},
                       "merge_into": {"type": "integer"}, "reason": {"type": "string"}},
        "required": ["story", "title", "decision", "merge_into", "reason"],
        "additionalProperties": False,
    }}},
    "required": ["decisions"],
    "additionalProperties": False,
}

CULTURE_ANSWER = {
    "type": "object",
    "properties": {"chosen": {"type": "array", "items": {
        "type": "object",
        "properties": {"story": {"type": "integer"}, "title": {"type": "string"}, "interest": {"type": "number"}, "reason": {"type": "string"}},
        "required": ["story", "title", "interest", "reason"],
        "additionalProperties": False,
    }}},
    "required": ["chosen"],
    "additionalProperties": False,
}

RATING_ANSWER = {
    "type": "object",
    "properties": {
        "ratings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "story": {"type": "integer"},
                    "headline": {"type": "string"},
                    **{name: {"type": "integer"} for name in RUBRIC},
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "new_today": {"type": "boolean"},
                    "stale": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["story", "headline", *RUBRIC, "action", "category", "new_today", "stale", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ratings"],
    "additionalProperties": False,
}

FINAL_ANSWER = {
    "type": "object",
    "properties": {
        "selected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "story": {"type": "integer"},
                    "title": {"type": "string"},
                    "headline": {"type": "string"},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "action": {"type": "string", "enum": [name for name in ACTIONS if name != "SKIP"]},
                    "what_happened": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "what_to_do": {"type": "string"},
                    "score": {"type": "number"},
                    "why_this_rank": {"type": "string"},
                },
                "required": ["rank", "story", "title", "headline", "category", "action", "what_happened", "why_it_matters",
                             "what_to_do", "score", "why_this_rank"],
                "additionalProperties": False,
            },
        },
        "not_selected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"story": {"type": "integer"}, "title": {"type": "string"}, "why_excluded": {"type": "string"}},
                "required": ["story", "title", "why_excluded"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["selected", "not_selected"],
    "additionalProperties": False,
}


class ScoreError(Exception):
    """The step could not run. The message says why."""


@dataclass
class ScoreResult:
    run_id: int
    run_date: date
    state: str  # scored, already_done
    stories: int
    rated: int
    report: Path
    chosen: int = 0  # stories on the editor's final list


def said(day: date | datetime) -> str:
    return f"{day:%A}, {day.day} {day:%B %Y}"


def collected(found: list, run_date: date, told: bool) -> str:
    """Where a story stands in the episode's window. This is worked out from when it was collected, which is
    certain, and not left to the editor to work out from publication dates, which are not."""
    first_seen = min(row.placed_on for row in found)
    if first_seen == run_date:
        return "new since the last episode"
    state = "already told in an episode" if told else "not yet told in an episode"
    return f"first seen {first_seen.isoformat()}, {state}, with new coverage since the last episode"


def since_last(found: list, run_date: date | None) -> list:
    """The items a story that began on an earlier day gained for this episode. Empty for a story that is all new."""
    if not run_date or all(row.placed_on == run_date for row in found):
        return []
    return [row for row in found if row.placed_on == run_date]


def description_of(found: list, limit: int = 500) -> str:
    """The longest description any of these items carries, cut to `limit` characters."""
    return max((row.summary or "" for row in found), key=len, default="")[:limit]


def listing(number: int, found: list, run_date: date | None = None, told: bool = False, opening: str | None = None) -> str:
    """One story as the editor sees it. Who reported it is shown, to judge how well supported it is; how it did on
    Hacker News is not, so that popularity cannot sway the score.

    The story's own title is always the first line: a rating is matched back to its story by that title.
    """
    titles = list(dict.fromkeys([found[0].story_title, *(row.title for row in found)]))[:3]
    description = description_of(found)
    dates = [row.published_at for row in found if row.published_at]
    sources = dict.fromkeys(f"{row.source} ({'discussion' if row.kind == 'traction' else row.kind})" for row in found)
    lines = [f"{number}. {titles[0]}"]
    if len(titles) > 1:
        lines.append("   Also reported as: " + " / ".join(titles[1:]))
    if dates:
        lines.append(f"   First published: {min(dates):%Y-%m-%d}")
    if run_date:
        lines.append("   Collected: " + collected(found, run_date, told))
    # A story that began on an earlier day shows its oldest headlines above, and its description may be an old one
    # too. What it gained since is set apart here, so that a new development is not hidden behind the older reports.
    new = since_last(found, run_date)
    if new:
        lines.append("   Reported since the last episode: " + " / ".join(dict.fromkeys(f"{row.title} ({row.source})" for row in new)))
        if description_of(new):
            lines.append(f"   Described since the last episode as: {description_of(new, 300)}")
    lines.append("   Sources: " + ", ".join(sources))
    lines.append(f"   {description}" if description else "   (no description available)")
    if opening:
        lines.append(f"   Opening of the article: {opening}")
    return "\n".join(lines)


def read_openings(engine, by_story: dict, run_date: date, read: Read) -> tuple[dict[int, str], int]:
    """The opening of one article for each story whose description says too little to judge it by:
    {story id: its first words}, and how many pages were read now.

    Hacker News gives a headline and no description, and on 9 October 2026 the editor scored a new DeepSeek model
    low as "too vague to judge" for that reason. The article read is the most authoritative of the story's items,
    and for a story that began earlier, one collected for this episode. An article already stored is not read again,
    and one that was refused is not asked for twice. A page that cannot be read leaves the story as it was.
    """
    wanted = {}
    for story_id, found in by_story.items():
        # A story that began earlier is judged on what is new, so what counts is how well that is described.
        judged_on = since_last(found, run_date) or found
        if len(description_of(judged_on).split()) < THIN_DESCRIPTION_WORDS:
            wanted[story_id] = min(judged_on, key=lambda row: (KIND_ORDER.get(row.kind, 9), row.id))
    with engine.connect() as conn:
        stored = {row.id: articles.get(conn, row.id) for row in wanted.values()}
    to_read = [row for row in wanted.values() if stored[row.id] is None]

    def attempt(row) -> tuple[str, str | None]:
        try:
            return read(row.url)
        except Exception:  # whatever goes wrong with one page, the story is still rated from its headline
            return "failed", None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, to_read))
    # What was read is kept, so that step 6 does not read the same page again.
    with engine.begin() as conn:
        for row, (status, text) in zip(to_read, results):
            articles.save(conn, row.id, status, text, datetime.now(timezone.utc))
    texts = {row.id: stored[row.id].text for row in wanted.values() if stored[row.id] is not None and stored[row.id].text}
    texts |= {row.id: text for row, (status, text) in zip(to_read, results) if status == "ok" and text}
    openings = {story_id: " ".join(texts[row.id].split()[:OPENING_WORDS]) for story_id, row in wanted.items() if row.id in texts}
    return openings, len(to_read)


def window_of(since: datetime | None) -> str:
    """What the editor is told the episode covers. The pipeline takes in everything it has not seen before, so an
    episode's window runs from the last run to this one, whatever the calendar says."""
    if since is None:
        return "This is the first episode, so it covers the last few days."
    return f"This episode covers everything collected since the last episode, which was made on {said(since)} at {since:%H:%M} UTC."


def rate(by_story: dict, run_date: date, days: int, rules: str, model_settings: dict, ask: model.Ask, since: datetime | None = None,
         covered: frozenset = frozenset(), openings: dict[int, str] | None = None) -> tuple[dict, list, list[str]]:
    """Ask the editor to score every story. Returns {story id: rating}, the replies, and what went wrong."""
    openings = openings or {}
    task = RATE_TASK.format(day=said(run_date), days=days, window=window_of(since))
    story_ids = list(by_story)
    ratings, replies, problems = {}, [], []
    for start in range(0, len(story_ids), BATCH):
        batch = story_ids[start:start + BATCH]
        message = task + "\n\n" + "\n\n".join(
            listing(number, by_story[story_id], run_date, story_id in covered, openings.get(story_id))
            for number, story_id in enumerate(batch, 1)
        )
        try:
            reply = ask(model_settings, rules, message, RATING_ANSWER)
        except model.ModelError as exc:
            problems.append(f"{len(batch)} stories were not rated: {exc}")
            continue
        replies.append(reply)
        for answer in reply.data.get("ratings", []):
            story_id = _story_meant(answer, batch, by_story, ratings)
            if story_id is not None:
                ratings[story_id] = {
                    **{name: min(10, max(0, int(answer.get(name) or 0))) for name in RUBRIC},
                    "action": answer.get("action") if answer.get("action") in ACTIONS else "WATCH",
                    "category": answer.get("category") if answer.get("category") in CATEGORIES else "Other",
                    "new_today": answer.get("new_today") is not False,
                    "stale": answer.get("stale") is True,
                    "reason": str(answer.get("reason") or "")[:200],
                }
        missing = sum(story_id not in ratings for story_id in batch)
        if missing:
            problems.append(f"{missing} stories could not be matched to a rating in the model's answer and are not rated")
    return ratings, replies, problems


def edit(candidates: list[int], by_story: dict, ratings: dict, worth: dict, recent: list[str], run_date: date, rules: str,
         model_settings: dict, ask: model.Ask) -> tuple[dict, dict, model.Reply]:
    """Ask the editor for the final list. `candidates` are story ids, best score first.

    Returns {story id: its place on the list and the editor's explanation}, {story id: why it was left out} for the
    strongest stories not selected, and the reply.
    """
    numbers = dict(enumerate(candidates, 1))
    message = EDIT_TASK.format(day=said(run_date))
    if recent:
        message += "\n\n" + RECENT_NOTE + "\n" + "\n".join(f"- {title}" for title in recent)
    message += "\n\n" + "\n\n".join(
        f"{number}. {by_story[story_id][0].story_title}\n"
        f"   Weighted score: {worth[story_id]:.2f} | Action: {ratings[story_id]['action']} | Category: {ratings[story_id]['category']} "
        f"| New since the last episode: {'yes' if ratings[story_id]['new_today'] else 'no'}\n"
        f"   {ratings[story_id]['reason']}"
        for number, story_id in numbers.items()
    )
    reply = ask(model_settings, rules, message, FINAL_ANSWER)
    final, near = {}, {}
    for answer in sorted(reply.data.get("selected", []), key=lambda answer: answer.get("rank") or 0):
        story_id = _candidate_meant(answer, numbers, by_story, final)
        if story_id is None:
            continue
        final[story_id] = {
            "rank": len(final) + 1,
            "headline": str(answer.get("headline") or "")[:200],
            "action": answer.get("action") if answer.get("action") in ACTIONS else ratings[story_id]["action"],
            "category": answer.get("category") if answer.get("category") in CATEGORIES else ratings[story_id]["category"],
            "what": str(answer.get("what_happened") or "")[:500],
            "why": str(answer.get("why_it_matters") or "")[:500],
            "do": str(answer.get("what_to_do") or "")[:500],
            "why_rank": str(answer.get("why_this_rank") or "")[:500],
        }
    for answer in reply.data.get("not_selected", []):
        story_id = _candidate_meant(answer, numbers, by_story, {**final, **near})
        if story_id is not None:
            near[story_id] = str(answer.get("why_excluded") or "")[:500]
    return final, near, reply


def _lines(numbers: dict, by_story: dict, ratings: dict, worth: dict) -> str:
    """The candidates of a later pass as the editor sees them: who reported each, its score and label, and what happened."""
    found = []
    for number, story_id in numbers.items():
        rating = ratings[story_id]
        sources = dict.fromkeys(f"{row.source} ({'discussion' if row.kind == 'traction' else row.kind})" for row in by_story[story_id])
        found.append(
            f"{number}. {by_story[story_id][0].story_title}\n"
            f"   Weighted score: {worth[story_id]:.2f} | Action: {rating['action']} | Category: {rating['category']} "
            f"| New since the last episode: {'yes' if rating['new_today'] else 'no'}\n"
            f"   Sources: {', '.join(sources)}\n"
            f"   {rating['reason']}"
        )
    return "\n\n".join(found)


def recover(lineup: list[int], remaining: list[int], by_story: dict, ratings: dict, worth: dict, recent: list[str], run_date: date,
            since: datetime | None, rules: str, model_settings: dict, ask: model.Ask) -> tuple[dict, model.Reply]:
    """Phase 2: look again at every story left off the final list. Returns {story id: {"decision", "reason", "into"}}.

    `lineup` is the final list in order. A story may be given a full segment, a quick brief, merged into a story
    of the list, or excluded, and each decision carries its reason.
    """
    numbers = dict(enumerate(remaining, 1))
    selected = dict(enumerate(lineup, 1))
    message = RECOVER_TASK.format(day=said(run_date), window=window_of(since))
    if recent:
        message += "\n\n" + RECENT_NOTE + "\n" + "\n".join(f"- {title}" for title in recent)
    message += "\n\nSelected:\n" + "\n".join(
        f"S{number}. {by_story[story_id][0].story_title}: {ratings[story_id]['reason']}" for number, story_id in selected.items()
    )
    message += "\n\nRemaining:\n\n" + _lines(numbers, by_story, ratings, worth)
    reply = ask(model_settings, rules, message, RECOVER_ANSWER)
    found = {}
    for answer in reply.data.get("decisions", []):
        story_id = _candidate_meant(answer, numbers, by_story, found)
        if story_id is None:
            continue
        decision = answer.get("decision") if answer.get("decision") in DECISIONS else "exclude"
        into = selected.get(answer.get("merge_into")) if decision == "merge" else None
        if decision == "merge" and into is None:
            decision = "exclude"  # merged into nothing that is on the list
        found[story_id] = {"decision": decision, "reason": str(answer.get("reason") or "")[:300], "into": into}
    return found, reply


def lighter_side(lineup: list[int], remaining: list[int], most: int, by_story: dict, ratings: dict, worth: dict, run_date: date,
                 since: datetime | None, rules: str, model_settings: dict, ask: model.Ask) -> tuple[dict, model.Reply]:
    """Phase 3: choose, from everything still out, the celebrity, viral and curiosity stories worth a place.
    Returns {story id: {"interest", "reason"}}, at most `most` of them."""
    numbers = dict(enumerate(remaining, 1))
    message = CULTURE_TASK.format(day=said(run_date), window=window_of(since), most=most)
    message += "\n\nIn the episode:\n" + "\n".join(f"- {by_story[story_id][0].story_title}" for story_id in lineup)
    message += "\n\nRemaining:\n\n" + _lines(numbers, by_story, ratings, worth)
    reply = ask(model_settings, rules, message, CULTURE_ANSWER)
    found = {}
    for answer in sorted(reply.data.get("chosen", []), key=lambda answer: -(answer.get("interest") or 0)):
        story_id = _candidate_meant(answer, numbers, by_story, found)
        if story_id is not None and len(found) < most:
            found[story_id] = {"interest": round(min(10.0, max(0.0, float(answer.get("interest") or 0))), 1),
                               "reason": str(answer.get("reason") or "")[:300]}
    return found, reply


def _same_words(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())[:40]


def _story_meant(answer: dict, batch: list[int], by_story: dict, taken: dict) -> int | None:
    """Which story of the batch a rating is for, or None if that cannot be told.

    The model returns a number and the headline. Its numbering can slip, which once put one story's rating on
    another, so the headline decides; the number only settles two stories with the same headline.
    """
    wanted = _same_words(str(answer.get("headline") or ""))
    matches = [story_id for story_id in batch if wanted and _same_words(by_story[story_id][0].story_title) == wanted and story_id not in taken]
    number = answer.get("story")
    numbered = batch[number - 1] if isinstance(number, int) and 1 <= number <= len(batch) else None
    if numbered in matches:
        return numbered
    return matches[0] if matches else None


def _candidate_meant(answer: dict, numbers: dict, by_story: dict, taken: dict) -> int | None:
    """Which candidate an entry of the final list is for. The title decides when it matches one; when the editor
    reworded it so that it matches none, the number is trusted. A story is never placed twice."""
    free = [story_id for story_id in numbers.values() if story_id not in taken]
    wanted = _same_words(str(answer.get("title") or ""))
    matches = [story_id for story_id in free if wanted and _same_words(by_story[story_id][0].story_title) == wanted]
    numbered = numbers.get(answer.get("story"))
    if matches:
        return numbered if numbered in matches else matches[0]
    return numbered if numbered in free else None


def rubric_of(settings: dict) -> dict:
    """The weights of the eight questions. A run started before the editor was brought in has the old five
    questions frozen in its settings, so it takes the weights of the instructions."""
    rubric = settings["score"]["rubric"]
    return rubric if all(name in rubric for name in RUBRIC) else RUBRIC


def importance_of(rating: dict | None, rubric: dict) -> float:
    """The weighted average of the eight ratings, 0 to 10. A story that was not rated has none."""
    if not rating:
        return 0.0
    return sum(rubric[name] * rating[name] for name in RUBRIC) / (sum(rubric[name] for name in RUBRIC) or 1)


def signals_of(found: list, run_date: date, focus, rating: dict | None, covered: bool = False) -> dict:
    """What is known about one story: the editor's rating, and the evidence counted from its items.

    A story that began on an earlier day and was never in an episode is judged on what is new today, so that
    Monday's coverage cannot carry it into Wednesday's episode on the strength of one late mention.
    """
    first_seen = min(row.placed_on for row in found)
    late = first_seen < run_date and not covered
    counted = [row for row in found if row.placed_on == run_date] if late else found
    traction = [row for row in counted if row.kind == "traction"]
    text = " ".join(f"{row.title} {row.summary or ''}" for row in found)
    return {
        "rating": rating,
        "first_seen": first_seen.isoformat(),
        "late": late,
        # Outlets are counted, not posts: three articles from one outlet count once. Hacker News is not an outlet.
        "outlet": len({row.source for row in counted if row.kind != "traction"}),
        "primary": int(any(row.kind == "primary" for row in counted)),
        "hn_points": max((row.points or 0 for row in traction), default=0),
        "hn_comments": max((row.comments or 0 for row in traction), default=0),
        # Earlier days on which the story also gained coverage.
        "staying": min(len({row.placed_on for row in found if row.placed_on < run_date}), MAX_STAYING_DAYS),
        "focus": int(bool(focus and focus.search(text))),
    }


def points_of(signals: dict, score_settings: dict, rubric: dict) -> dict:
    """Each signal scaled and weighted: the editor's score, and the evidence beside it."""
    scaled = {
        "importance": importance_of(signals["rating"], rubric),
        "outlet": min(signals["outlet"], MAX_OUTLETS),
        "primary": signals["primary"],
        "hn_points": math.log10(1 + signals["hn_points"]),
        "hn_comments": math.log10(1 + signals["hn_comments"]),
        "staying": signals["staying"],
        "focus": signals["focus"],
    }
    return {name: round(score_settings["weights"][name] * scaled[name], 2) for name in POINTS}


def evidence_of(points: dict) -> float:
    return sum(value for name, value in points.items() if name != "importance")


def traction_of(points: dict, score_settings: dict) -> float:
    """What Hacker News adds to a rated story's score: its points and comments at their usual weights, and never
    more than `traction_max`. Traction shows that readers care. A story without a thread is not marked down for
    it: it simply keeps the editor's score."""
    return round(min(score_settings.get("traction_max", 0), points["hn_points"] + points["hn_comments"]), 2)


def total_of(signals: dict, points: dict, score_settings: dict) -> float:
    """A rated story's score is the editor's score plus what Hacker News adds; how many outlets covered it adds
    nothing. Only a story that was not rated, because no model is chosen or its request failed, is
    placed by its evidence."""
    if not signals["rating"]:
        return round(evidence_of(points), 2)
    return round(points["importance"] + traction_of(points, score_settings), 2)


def topic_of(found: list, topics: dict) -> str | None:
    """The topic whose words appear most in the story's titles and descriptions; the first listed wins a tie."""
    text = " ".join(f"{row.title} {row.summary or ''}" for row in found)
    counts = {name: len(phrase_pattern(words).findall(text)) for name, words in topics.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] else None


def score(run_date: date, *, root: Path = ROOT, ask: model.Ask | None = None, read: Read | None = None) -> ScoreResult:
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if STEP - 1 not in done:
                raise ScoreError(f"There are no grouped stories for {run_date}. Run step 4 first.")
            if STEP in done:
                return ScoreResult(run.id, run_date, "already_done", 0, 0, report)
            runlog.begin_step(conn, run.id, STEP)
            by_story = scores.items_of(conn, scores.active_stories(conn, run.run_date))
            covered, _ = selections.covered_before(conn, run.run_date)
            recent = selections.recent_titles(conn, run.run_date)
            before = runlog.last_before(conn, run.run_date)

        # The run's frozen settings are used, not the files. No transaction is open while the model works.
        settings = run.settings
        rubric = rubric_of(settings)
        model_settings = model.chosen(settings, root)
        if ask is None and model.configured(model_settings):
            ask = model.ask
            if read is None:
                # Imported here: only a real run reads pages, and tests bring their own stand-in.
                from steps.step06_select.step import Reader
                read = Reader().read
        ratings, replies, problems = {}, [], []
        openings, opened = {}, 0
        if ask and by_story:
            rules = EDITOR.read_text(encoding="utf-8")
            if read:
                openings, opened = read_openings(engine, by_story, run.run_date, read)
            ratings, replies, problems = rate(
                by_story, run.run_date, settings["collect"]["max_age_days"], rules, model_settings, ask,
                before.started_at if before else None, frozenset(covered), openings,
            )

        focus = phrase_pattern(settings["score"]["focus"]) if settings["score"].get("focus") else None
        signals = {story_id: signals_of(found, run.run_date, focus, ratings.get(story_id), story_id in covered) for story_id, found in by_story.items()}
        points = {story_id: points_of(signals[story_id], settings["score"], rubric) for story_id in by_story}

        # The final list: the editor sees the stories it did not mark SKIP, best score first. Stories with the same
        # score are put in the order of their evidence, which is the only thing coverage decides.
        final, final_reply = {}, None
        candidates = sorted(
            (story_id for story_id, rating in ratings.items() if rating["action"] != "SKIP"),
            key=lambda story_id: (-points[story_id]["importance"], -evidence_of(points[story_id])),
        )[:MAX_CANDIDATES]
        if candidates:
            worth = {story_id: points[story_id]["importance"] for story_id in candidates}
            try:
                final, near, final_reply = edit(candidates, by_story, ratings, worth, recent, run.run_date, rules, model_settings, ask)
            except model.ModelError as exc:
                problems.append(
                    f"The final list could not be made: {exc} Step 6 takes the stories marked Act now or Know today instead, best score first."
                )
            else:
                for story_id, entry in final.items():
                    ratings[story_id].update(final=entry, action=entry["action"], category=entry["category"])
                for story_id, why in near.items():
                    ratings[story_id]["near_miss"] = why
                if not final:
                    problems.append("The editor's final list was empty or could not be matched to the stories.")

        # Phases 2 and 3, each a pass of its own over what the final list left out. The final list is phase 1 and
        # stays as it is: these two can add to the episode after it, never reorder it.
        since = before.started_at if before else None
        everything = {story_id: points[story_id]["importance"] for story_id in ratings}
        by_worth = sorted(ratings, key=lambda story_id: (-everything[story_id], -evidence_of(points[story_id])))
        first = sorted(final, key=lambda story_id: final[story_id]["rank"])
        recovered, chosen, extra_replies = {}, {}, []
        left = [story_id for story_id in by_worth if story_id not in final]
        if final and left:
            try:
                recovered, reply = recover(first, left, by_story, ratings, everything, recent, run.run_date, since,
                                           rules + "\n\n---\n\n" + RECOVERY.read_text(encoding="utf-8"), model_settings, ask)
                extra_replies.append(("recover", reply))
            except model.ModelError as exc:
                problems.append(f"The recovery pass (phase 2) could not be made: {exc} The episode keeps to the final list.")
            for story_id, entry in recovered.items():
                ratings[story_id]["recovery"] = entry
                # The reason a story stays out is the recovery pass's, which looked at every one of them.
                if entry["decision"] == "exclude" and ratings[story_id]["action"] != "SKIP":
                    ratings[story_id]["near_miss"] = entry["reason"]
                elif entry["decision"] != "exclude":
                    ratings[story_id].pop("near_miss", None)
        second = [story_id for story_id in by_worth if recovered.get(story_id, {}).get("decision") in ("full", "brief")]
        second.sort(key=lambda story_id: recovered[story_id]["decision"] != "full")  # full segments before quick briefs
        merged = {story_id for story_id in recovered if recovered[story_id]["decision"] == "merge"}
        most = settings["select"].get("culture_max", 0)
        left = [story_id for story_id in by_worth if story_id not in final and story_id not in second and story_id not in merged]
        if final and left and most:
            try:
                chosen, reply = lighter_side(first + second, left, most, by_story, ratings, everything, run.run_date, since,
                                             rules + "\n\n---\n\n" + CULTURE.read_text(encoding="utf-8"), model_settings, ask)
                extra_replies.append(("culture", reply))
            except model.ModelError as exc:
                problems.append(f"The lighter-side pass (phase 3) could not be made: {exc} The episode has no such stories.")
            for story_id, entry in chosen.items():
                ratings[story_id]["culture"] = entry
                ratings[story_id].pop("near_miss", None)
        # The episode's lineup: phase 1 in the editor's order, then phase 2, then phase 3.
        placed = [(story_id, 1, "full") for story_id in first]
        placed += [(story_id, 2, "recovered" if recovered[story_id]["decision"] == "full" else "brief") for story_id in second]
        placed += [(story_id, 3, "culture") for story_id in chosen]
        for rank, (story_id, phase, form) in enumerate(placed, 1):
            ratings[story_id]["lineup"] = {"rank": rank, "phase": phase, "as": form}

        with engine.begin() as conn:
            for story_id, found in by_story.items():
                scores.save(
                    conn, run.id, story_id, total_of(signals[story_id], points[story_id], settings["score"]), topic_of(found, settings["topics"]),
                    signals[story_id], points[story_id],
                )
            for reply in replies:
                model.record(conn, run.id, STEP, "rate", reply)
            if final_reply:
                model.record(conn, run.id, STEP, "edit", final_reply)
            for purpose, reply in extra_replies:
                model.record(conn, run.id, STEP, purpose, reply)

            ranked = scores.ranked(conn, run.id)
            summary = f"{len(ranked)} stories scored, {len(ratings)} rated by the editor, {len(final)} on the final list"
            if second or merged or chosen:
                summary += f", {len(second)} recovered, {len(merged)} merged, {len(chosen)} for the lighter side"
            lines = _report_lines(run_date, summary, ranked, settings, rubric, model_settings, problems, scores.topic_counts(conn, run.run_date),
                                  (len(openings), opened))
            runlog.finish_step(conn, run.id, STEP, detail=summary)
    except SQLAlchemyError as exc:
        raise ScoreError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    write_report(root, run_date, STEP, lines)
    return ScoreResult(run.id, run_date, "scored", len(ranked), len(ratings), report, len(placed))


def _cell(text: str) -> str:
    return text.replace("|", "/")


def _report_lines(run_date: date, summary: str, ranked: list, settings: dict, rubric: dict, model_settings: dict, problems: list, topics: list,
                  openings: tuple[int, int] = (0, 0)) -> list[str]:
    weights, limits = settings["score"]["weights"], settings["select"]
    rated = any(row.signals["rating"] for row in ranked)
    listed = sorted((row for row in ranked if (row.signals["rating"] or {}).get("final")), key=lambda row: row.signals["rating"]["final"]["rank"])
    close = [row for row in ranked if (row.signals["rating"] or {}).get("near_miss")]
    lines = [f"# Step 5, Score: {run_date.isoformat()}", "", f"{summary}.", ""]
    if rated:
        lines += [
            f"Each story is judged by the editor ({model_settings.get('name')}, instructions in `steps/step05_score/editor.md`) on "
            "eight questions, 0 to 10. Its score is their weighted average. How many outlets covered a story adds nothing to "
            f"its score. Hacker News points and comments add to it, at most {settings['score'].get('traction_max', 0):g}. A story "
            "with no Hacker News thread loses nothing.",
        ]
    else:
        lines += [
            "**No story was rated, because no model is chosen.** The ranking below rests on the evidence alone "
            "(outlets, a primary source, Hacker News traction), which cannot tell an important story from a minor one.",
        ]
    if openings[0]:
        lines += [
            "",
            f"{openings[0]} {'story' if openings[0] == 1 else 'stories'} had no description to judge by, so the editor was shown the "
            f"opening of the article instead ({openings[1]} pages read now).",
        ]
    lines += [f"- {problem}" for problem in problems]
    lines += [""]
    if listed:
        lines += [
            "## Top AI news today",
            "",
            f"The editor's final list. Step 6 takes these stories in this order, up to {limits['max_stories']}, leaving out any that "
            f"score under {limits['min_score']:g}.",
            "",
        ]
        for row in listed:
            entry = row.signals["rating"]["final"]
            lines += [
                f"### #{entry['rank']} — {entry['headline']}",
                "",
                f"{ACTIONS[entry['action']]} · {entry['category']} · score {row.total:g}",
                "",
                f"- **What happened:** {entry['what']}",
                f"- **Why it matters:** {entry['why']}",
                f"- **What the audience can do:** {entry['do']}",
                f"- **Why this rank:** {entry['why_rank']}",
                f"- **Story:** {row.title}",
                "",
            ]
    elif rated:
        lines += [f"There is no final list. Step 6 takes the stories marked Act now or Know today that score {limits['min_score']:g} or more.", ""]
    else:
        lines += [f"The episode takes the top {limits['max_stories']} stories.", ""]
    titles = {row.story_id: row.title for row in ranked}
    looked = [row for row in ranked if (row.signals["rating"] or {}).get("recovery")]
    back = [row for row in looked if row.signals["rating"]["recovery"]["decision"] != "exclude"]
    if looked:
        said_as = {"full": "Full segment", "brief": "Quick brief", "merge": "Merged"}
        lines += [
            "## Phase 2: recovered from the rest",
            "",
            f"The recovery pass looked again at all {len(looked)} stories the final list left out, so that a worthwhile one is not "
            f"lost. It brought back {sum(row.signals['rating']['recovery']['decision'] in ('full', 'brief') for row in looked)} and merged "
            f"{sum(row.signals['rating']['recovery']['decision'] == 'merge' for row in looked)} into stories on the list. They come after "
            "the final list in the episode.",
            "",
        ]
        if back:
            lines += ["| Decision | Score | Story | Reason |", "| --- | --- | --- | --- |"]
            for row in sorted(back, key=lambda row: list(said_as).index(row.signals["rating"]["recovery"]["decision"])):
                entry = row.signals["rating"]["recovery"]
                into = f" into \"{_cell(titles.get(entry['into'], ''))}\"" if entry["decision"] == "merge" else ""
                lines.append(f"| {said_as[entry['decision']]}{into} | {row.total:g} | {_cell(row.title)} | {_cell(entry['reason'])} |")
            lines += [""]
    lighter = sorted((row for row in ranked if (row.signals["rating"] or {}).get("culture")), key=lambda row: -row.signals["rating"]["culture"]["interest"])
    if lighter:
        lines += [
            "## Phase 3: the lighter side",
            "",
            "Celebrity, viral and curiosity stories, judged on their own terms. They come last in the episode.",
            "",
            "| Interest | Score | Story | Why it is worth telling |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            f"| {row.signals['rating']['culture']['interest']:g} | {row.total:g} | {_cell(row.title)} | {_cell(row.signals['rating']['culture']['reason'])} |"
            for row in lighter
        ]
        lines += [""]
    if close:
        lines += ["## Not selected", "", "Stories the editor labelled worth a look that still stayed out, and why.", ""]
        lines += [f"- **{row.title}** ({row.total:g}): {row.signals['rating']['near_miss']}" for row in close]
        lines += [""]

    lines += [
        "## Every story scored",
        "",
        "| # | Score | Action | Category | Final | Story | What happened |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rank, row in enumerate(ranked, 1):
        rating = row.signals["rating"]
        action = ACTIONS[rating["action"]] + (" (old news)" if rating["stale"] else "") if rating else "not rated"
        what = (rating or {}).get("reason", "")
        if row.signals["late"]:
            what = f"{what} (first seen {row.signals['first_seen']}; only today's coverage is counted)".strip()
        place = ""
        if rating and rating.get("lineup"):
            place = f"#{rating['lineup']['rank']}" + {1: "", 2: " (recovered)", 3: " (lighter side)"}[rating["lineup"]["phase"]]
        elif rating and rating.get("final"):
            place = f"#{rating['final']['rank']}"
        elif rating and (rating.get("recovery") or {}).get("decision") == "merge":
            place = "merged"
        lines.append(
            f"| {rank} | {row.total:g} | {action} | {(rating or {}).get('category', '')} | {place} | {_cell(row.title)} | {_cell(what)} |"
        )
    lines += [
        "",
        "## The eight ratings behind each score",
        "",
        "| # | Story | " + " | ".join(ASKED.values()) + " | Editor's score | HN points | Added for Hacker News |",
        "| --- | --- | " + " | ".join("---" for _ in ASKED) + " | --- | --- | --- |",
    ]
    lines += [
        f"| {rank} | {_cell(row.title)} | " + " | ".join(str(row.signals["rating"][name]) for name in RUBRIC)
        + f" | {row.points['importance']:g} | {row.signals['hn_points'] or ''} | {traction_of(row.points, settings['score']) or ''} |"
        for rank, row in enumerate(ranked, 1) if row.signals["rating"]
    ]
    lines += [
        "",
        "## Weights used",
        "",
        "| Question | Weight |",
        "| --- | --- |",
        *(f"| {ASKED[name]} | {rubric[name]:g} |" for name in RUBRIC),
        "",
        "A story that was not rated is placed by its evidence instead:",
        "",
        "| Evidence | Weight | Applied to |",
        "| --- | --- | --- |",
        f"| Outlet | {weights['outlet']:g} | each independent outlet, at most {MAX_OUTLETS}; Hacker News is not one |",
        f"| Primary | {weights['primary']:g} | once, if the organisation itself announced it |",
        f"| HN points | {weights['hn_points']:g} | log10(1 + points) |",
        f"| HN comments | {weights['hn_comments']:g} | log10(1 + comments) |",
        f"| Earlier days | {weights['staying']:g} | each earlier day with coverage, up to {MAX_STAYING_DAYS} |",
        f"| Focus | {weights['focus']:g} | once, if it matches a focus area |",
        "",
        "## Topics over the past 7 days",
        "",
        "| Topic | Stories |",
        "| --- | --- |",
        *(f"| {name} | {count} |" for name, count in topics),
    ]
    return lines
