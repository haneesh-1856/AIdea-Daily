"""Step 8's part of the longer episodes: plan the segments once, then write each format segment by segment."""

import re
from datetime import date

from sqlalchemy import Engine

from common import episodes, formats, model
from common.text import word_count
from steps.formats import prompts
from steps.step08_write.step import spoken_date, story_message

STEP = 8
SEGMENT_MOST = 1100  # words: a longer segment is split by the planner, so that one request never writes too much
# What the linking segments take when the plan is made by code, and the fewest words any segment is given.
BOOKENDS = {"cold_open": ("Cold open", 180), "intro": ("Introduction", 160), "closing": ("Closing takeaway", 220)}
LEAST_WORDS = 80
# The segments of a plan made by code, from where step 7 placed each story.
FALLBACK_TITLES = {
    "corrections": "Corrections first", "main": "The biggest stories", "quick_hits": "Quick catch-up",
    "culture": "The interesting side of AI", "watching": "Worth watching",
}
TRIES = 2  # a request that fails is made once more


def target_words(settings: dict) -> tuple[int, int]:
    """The fewest and the most spoken words the plan should aim for, from the wanted minutes and the speaking pace."""
    least = settings["formats"]["min_minutes"] * settings["formats"]["speaking_pace"]
    return least, int(least * 1.15)


def plan_message(day: date, written: list, have: dict) -> str:
    lines = [f"Episode date: {spoken_date(day)}", "", f"Today's {len(written)} selected stories, most important first:"]
    for number, entry in enumerate(sorted(written, key=lambda entry: entry.rank), 1):
        sources, _ = entry.material
        lines += [
            f"{number}. {entry.title}",
            f"   Rank {entry.rank}, score {entry.score:g}, {entry.kind}, {entry.label}, "
            f"{sum(word_count(row.article_text or row.summary) for row in sources)} words of source text",
            f"   Headline: {have[entry.story_id].headline}",
            f"   Brief: {have[entry.story_id].brief}",
        ]
    return "\n".join(lines)


def tidy_plan(data: dict, ranked: list) -> list[dict]:
    """The model's plan made safe to write from: every story told exactly once, the linking segments in their places.

    A story the plan forgot is added to a catch-up segment, and one it named twice is told the first time only.
    """
    seen: set[int] = set()
    middle = []
    for segment in data.get("segments") or []:
        if segment.get("kind") != "stories":
            continue
        numbers = [n for n in segment.get("stories") or [] if isinstance(n, int) and 1 <= n <= len(ranked) and n not in seen]
        numbers = list(dict.fromkeys(numbers))
        seen.update(numbers)
        if numbers:
            middle.append({"kind": "stories", "title": (segment.get("title") or "").strip() or "More of today's stories",
                           "angle": (segment.get("angle") or "").strip(), "story_ids": [ranked[n - 1].story_id for n in numbers],
                           "words": segment.get("words")})
    missed = [entry.story_id for number, entry in enumerate(ranked, 1) if number not in seen]
    if missed:
        middle.append({"kind": "stories", "title": FALLBACK_TITLES["quick_hits"], "angle": "", "story_ids": missed, "words": 110 * len(missed)})

    given = {segment.get("kind"): segment for segment in data.get("segments") or [] if segment.get("kind") in BOOKENDS}
    def bookend(kind: str) -> dict:
        title, words = BOOKENDS[kind]
        segment = given.get(kind) or {}
        return {"kind": kind, "title": (segment.get("title") or "").strip() or title, "angle": (segment.get("angle") or "").strip(),
                "story_ids": [], "words": segment.get("words") or words}

    plan = [bookend("cold_open"), bookend("intro"), *middle, bookend("closing")]
    for segment in plan:
        words = segment["words"] if isinstance(segment["words"], int) else 0
        segment["words"] = max(LEAST_WORDS, min(SEGMENT_MOST, words))
    return plan


def fallback_plan(ranked: list, settings: dict) -> list[dict]:
    """A plan made by code when the model could not be asked: the stories grouped as step 7 placed them."""
    groups: dict[str, list] = {}
    for entry in ranked:
        groups.setdefault(entry.segment if entry.segment in FALLBACK_TITLES else "main", []).append(entry)
    segments = []
    for name in FALLBACK_TITLES:
        for start in range(0, len(groups.get(name, [])), 4):  # at most four stories to a segment
            inside = groups[name][start:start + 4]
            # About twice the room the regular episode gives each story, since here it is explained as well as told.
            words = sum(2 * episodes.story_room(entry, settings, 0, len(ranked))[0] for entry in inside)
            segments.append({"kind": "stories", "title": FALLBACK_TITLES[name], "stories": [ranked.index(entry) + 1 for entry in inside],
                             "angle": "", "words": words})
    return tidy_plan({"segments": segments}, ranked)


def running_order(plan: list, titles: dict[int, str]) -> str:
    lines = []
    for segment in plan:
        lines.append(f"{segment.position}. {segment.title}" + (f": {segment.angle}" if segment.angle else ""))
        lines += [f"   - {titles[story_id]}" for story_id in segment.story_ids]
    return "\n".join(lines)


def ending(lines: list[dict] | None, limit: int = 60) -> str:
    """The last words of a segment, so that the next one can pick up from them."""
    words = " ".join(f"{line['speaker']}: {line['text']}" for line in (lines or [])[-2:]).split()
    return " ".join(words[-limit:])


def segment_message(day: date, show: str, plan: list, segment, before, by_story: dict, have: dict, limit: int) -> str:
    titles = {story_id: entry.title for story_id, entry in by_story.items()}
    parts = [
        f"Show: {show}", f"Date: {spoken_date(day)}", "",
        f"Running order (you are writing segment {segment.position}):", running_order(plan, titles), "",
    ]
    if before is not None and before.lines:
        parts += [f"The segment before yours ended: \"{ending(before.lines)}\"", ""]
    parts += [f"Your segment: {segment.position}. {segment.title}"]
    parts += [f"Angle: {segment.angle}"] if segment.angle else []
    parts += [f"Length: about {segment.words} words", ""]
    if segment.kind != "stories":
        # The linking segments draw on the whole day. They are given each story as the regular script tells it.
        parts.append(f"Today's {len(by_story)} stories, most important first:")
        for entry in sorted(by_story.values(), key=lambda entry: entry.rank):
            summary = have[entry.story_id]
            note = "" if entry.kind == "new" else f", {entry.kind}"
            note += ", unconfirmed" if entry.label == "rumour" else ""
            parts += ["", f"{entry.title} (rank {entry.rank}{note})", summary.what_happened]
            parts += [summary.differences] if summary.differences and summary.differences != "Coverage broadly agrees." else []
        return "\n".join(parts)
    parts.append("Stories to tell, in this order:")
    for number, story_id in enumerate(segment.story_ids, 1):
        entry = by_story[story_id]
        sources, earlier = entry.material
        parts += ["", f"===== Story {number} of {len(segment.story_ids)} (rank {entry.rank} of {len(by_story)} today) =====",
                  story_message(entry, sources, earlier, limit)]
    return "\n".join(parts)


def clean_lines(data: dict, speakers: tuple) -> list[dict]:
    """The lines of the model's answer that can be spoken, with anything that is not speech taken out."""
    lines = []
    for line in data.get("lines") or []:
        text = re.sub(r"[*#`_]", "", line.get("text") or "")
        # Only the voice model's own tags may stand in brackets; any other bracketed word is a stage direction.
        text = re.sub(r"\[[^\]]*\]", lambda m: m.group() if formats.TAG.fullmatch(m.group()) else " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(speakers) == 1:
            text = formats.plain(text)
        if formats.plain(text):
            lines.append({"speaker": line.get("speaker") if line.get("speaker") in speakers else speakers[-1], "text": text})
    return lines


class _Entry:
    """A story of the lineup with the material it is written from."""

    def __init__(self, entry, material: tuple):
        self._entry, self.material = entry, material

    def __getattr__(self, name):
        return getattr(self._entry, name)


def _ask(ask, settings: dict, rules: str, message: str, answer: dict) -> tuple[model.Reply | None, str | None]:
    error = None
    for _ in range(TRIES):
        try:
            return ask(settings["model"], rules, message, answer), None
        except model.ModelError as exc:
            error = str(exc)
    return None, error


def write_formats(engine: Engine, run, settings: dict, written: list, have: dict, material: dict, ask) -> list[str]:
    """Write the longer episodes of the day. Returns one line per format saying what was written.

    Everything is saved as soon as it is written, so a run that stops here writes only what is missing when it
    resumes. A format the model fails on is left unfinished and reported; the regular episode does not depend on it.
    """
    wanted = formats.wanted(settings)
    if not wanted or not written:
        return []
    chosen = settings["formats"]
    show = chosen["show_name"]
    ranked = sorted((_Entry(entry, material[entry.story_id]) for entry in written), key=lambda entry: entry.rank)
    by_story = {entry.story_id: entry for entry in ranked}

    with engine.begin() as conn:
        for name in wanted:
            formats.begin(conn, run.id, name)
        planned = {name: formats.segments_of(conn, run.id, name) for name in wanted}
    if not all(planned.values()):
        # One plan serves every format, so that they tell the same stories in the same order.
        least, most = target_words(settings)
        rules = prompts.PLAN_RULES.format(show=show, segment_most=SEGMENT_MOST, least=least, most=most, minutes=chosen["min_minutes"])
        reply, error = _ask(ask, settings, rules, plan_message(run.run_date, ranked, have), prompts.PLAN_ANSWER)
        plan = tidy_plan(reply.data, ranked) if reply else fallback_plan(ranked, settings)
        shortfall = (reply.data.get("shortfall") or "").strip() if reply else f"the plan was made by code, because the request for it failed: {error}"
        with engine.begin() as conn:
            if reply:
                model.record(conn, run.id, STEP, "formats plan", reply)
            for name in wanted:
                if not planned[name]:
                    formats.save_plan(conn, run.id, name, plan)
                    formats.update(conn, run.id, name, shortfall=shortfall or None)

    said = []
    for name in wanted:
        speakers = formats.FORMATS[name]["speakers"]
        with engine.begin() as conn:
            formats.update(conn, run.id, name, note=None)
            plan = formats.segments_of(conn, run.id, name)
        error = None
        for place, segment in enumerate(plan):
            if segment.lines:
                continue
            rules = prompts.RULES[name].format(show=show, words=segment.words) + "\n\n" + prompts.KIND_RULES[segment.kind]
            message = segment_message(run.run_date, show, plan, segment, plan[place - 1] if place else None, by_story, have,
                                      settings["write"]["max_source_words"])
            reply, error = _ask(ask, settings, rules, message, prompts.segment_answer(speakers))
            lines = clean_lines(reply.data, speakers) if reply else []
            if reply and not lines:
                error = "the model returned no lines"
            with engine.begin() as conn:
                if reply:
                    model.record(conn, run.id, STEP, name, reply)
                if lines:
                    formats.save_lines(conn, segment.id, lines, [str(one) for one in reply.data.get("illustrations") or []])
                    plan = formats.segments_of(conn, run.id, name)
                else:
                    # The segments after this one pick up from it, so the format stops here.
                    formats.update(conn, run.id, name, note=f"segment {segment.position}, {segment.title}, could not be written: {error}")
            if not lines:
                break
        label = formats.FORMATS[name]["name"]
        if formats.written(plan):
            said.append(f"{label} script {sum(formats.spoken_words(segment.lines) for segment in plan)} words")
        else:
            said.append(f"{label} script not finished")
    return said
