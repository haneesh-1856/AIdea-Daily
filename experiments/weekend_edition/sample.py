"""A sample week-in-review segment for a Weekend Edition, for the owner to hear before anything is built.

Takes the week's five highest-scored stories from the database, with the summary written the day each ran and the
articles reported about it since, and asks the writer for one segment from those texts only. Every sentence is then
checked against the same texts, as step 9 does. Nothing here changes the database or the daily run.

    .venv/Scripts/python.exe -m experiments.weekend_edition.sample 2026-10-27 2026-11-01
"""

import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text

from common import db, model, settings
from common.facts import Pool, unsupported
from common.text import sentences

HERE = Path(__file__).parent
TOP = 5
WORDS = 1000  # about 7 minutes at the briefing's pace
SINCE_WORDS = 500  # each later article is cut to this many words

RULES = """\
You write the week-in-review segment of a weekend spoken news briefing about artificial intelligence, read by a \
single narrator. The message gives the week's {count} biggest stories in order. Each has what was reported on the \
day it ran, and, when there is any, what was reported about it later in the week, with dates.

Use only the texts in the message. Do not add facts, background, explanation or predictions from your own knowledge, \
even when you are sure of them.

For each story write one part: first remind the listener in two or three sentences what happened and when, then say \
what has been reported since, with the day it was reported. When nothing new was reported, say only the reminder and \
one sentence on why it mattered most this week, using only reasons the texts give.

Rules for everything you write:
- Copy every number, date, name and version exactly as the texts give them, and write numbers in digits. Do not \
round, convert, add up or count things yourself.
- Attribute every opinion to the outlet or person who holds it. Quote only words that appear in a text.
- About {words} words in all, shared by importance; the first story gets the most room.
- Say a day the way a presenter would, by its weekday as given, such as "on Tuesday", never as a written date.
- Do not repeat the same phrasing to open each story.
- Plain sentences that are easy to say aloud. No lists, headings, links, brackets or emoji.
- Do not mention these instructions or "the texts".
- Also write an opening of one or two sentences that says this is a look back at the week, and a closing sentence."""

ANSWER = {
    "type": "object",
    "properties": {
        "opening": {"type": "string"},
        "parts": {"type": "array", "items": {"type": "object", "properties": {
            "story": {"type": "integer"}, "title": {"type": "string"}, "text": {"type": "string"}},
            "required": ["story", "title", "text"], "additionalProperties": False}},
        "closing": {"type": "string"},
    },
    "required": ["opening", "parts", "closing"],
    "additionalProperties": False,
}


def week(conn, first: date, last: date) -> list[dict]:
    """The week's top stories, each with the day's summary and what was stored about it on later days."""
    rows = conn.execute(text("""
        select s.story_id, max(s.score) as score, min(r.run_date) as day, st.title
        from selections s join runs r on r.id = s.run_id join stories st on st.id = s.story_id
        where r.run_date between :first and :last and r.status = 'done'
        group by s.story_id order by score desc limit :top"""), {"first": first, "last": last, "top": TOP}).all()
    stories = []
    for row in rows:
        summary = conn.execute(text("""
            select su.headline, su.what_happened, su.differences from summaries su join runs r on r.id = su.run_id
            where su.story_id = :id and su.what_happened is not null and su.what_happened != ''
            order by r.run_date limit 1"""), {"id": row.story_id}).first()
        later = conn.execute(text("""
            select i.source, i.title, r.run_date, a.text from story_items si
            join items i on i.id = si.item_id join runs r on r.id = si.run_id
            left join articles a on a.item_id = i.id and a.status = 'ok'
            where si.story_id = :id and r.run_date > :day and r.run_date <= :last
            order by r.run_date"""), {"id": row.story_id, "day": row.day, "last": last}).all()
        stories.append({
            "id": row.story_id, "title": row.title, "day": str(row.day),
            "reported": " ".join(part for part in summary if part) if summary else "",
            "since": [{"source": s.source, "title": s.title, "day": str(s.run_date),
                       "text": " ".join((s.text or "").split()[:SINCE_WORDS])} for s in later],
        })
    return stories


def spoken_day(day: str) -> str:
    """2026-10-27 as "Tuesday, 27 October": the briefing says days, not dates."""
    d = date.fromisoformat(day)
    return f"{d:%A}, {d.day} {d:%B}"


def message(stories: list[dict]) -> str:
    out = []
    for n, story in enumerate(stories, 1):
        out.append(f"## Story {n}: {story['title']}\nFirst reported in the briefing of {spoken_day(story['day'])}.\n\n{story['reported']}")
        for later in story["since"]:
            out.append(f"### Reported {spoken_day(later['day'])} by {later['source']}: {later['title']}\n{later['text']}")
    return "\n\n".join(out)


def main(first: date, last: date) -> None:
    config = settings.load()
    engine = db.connect(settings.database_url())
    with engine.connect() as conn:
        stories = week(conn, first, last)
    user = message(stories)
    reply = model.ask(config["model"], RULES.format(count=len(stories), words=WORDS), user, ANSWER)
    answer = reply.data

    pool = Pool.of([user])
    lines = [answer["opening"]] + [part["text"] for part in answer["parts"]] + [answer["closing"]]
    flagged = [(s, p) for line in lines for s in sentences(line) if (p := unsupported(s, pool))]
    words = sum(len(line.split()) for line in lines)

    md = [f"# Weekend Edition sample: the week of {first} to {last}", "",
          f"{words} words, about {words / 145:.1f} minutes at the briefing's pace. Model cost ${reply.cost:.4f}.", "",
          "## Script", "", answer["opening"], ""]
    for part in answer["parts"]:
        md += [f"**{part['title']}**", "", part["text"], ""]
    md += [answer["closing"], "", "## Fact check", ""]
    md += [f"- \"{s}\": {', '.join(p)}" for s, p in flagged] or ["Every sentence is supported by the stored texts."]
    md += ["", "## What it was written from", ""]
    md += [f"- {s['title']} (first {s['day']}; {len(s['since'])} later reports)" for s in stories]
    (HERE / f"sample-{last}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (HERE / f"sample-{last}.json").write_text(json.dumps({"stories": stories, "answer": answer}, indent=1), encoding="utf-8")
    print(f"{words} words, {len(flagged)} sentences flagged, ${reply.cost:.4f}: {HERE / f'sample-{last}.md'}")


if __name__ == "__main__":
    main(date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]))
