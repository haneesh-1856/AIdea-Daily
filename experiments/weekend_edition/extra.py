"""More stories for a short day: stories the editor rated but passed over, written for the briefing and the podcast.

Written from the stored articles with the daily writers' rules and checked against them. Nothing is stored in the
database; the text goes to extra-<date>.json and extra-<date>.md for speaking and splicing by hand.

    .venv/Scripts/python.exe -m experiments.weekend_edition.extra 2026-11-02 1581 1567 1563 1572 1565 1564 1573
"""

import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text

from common import db, model, settings
from common.facts import Pool, unsupported
from common.text import sentences
from steps.formats import prompts

HERE = Path(__file__).parent
SOURCE_WORDS = 1200
# The podcast's extra stories in three segments, so that no one request writes too much: (stories, words).
SEGMENTS = [((0, 1, 2), 1000), ((3, 4), 800), ((5, 6), 800)]

BRIEF_RULES = """\
You write a short "More from today" run of quick items for a daily spoken news briefing about artificial \
intelligence, read by a single narrator. These are smaller stories that did not make the main list.

Use only the texts in the message. Do not add facts, background or predictions from your own knowledge.
- Write one opening sentence that leads into a few more stories from today, and one item per story, in the order given.
- Each item is two or three sentences, about 40 words: what happened and who says so.
- Copy every number, date, name and version exactly as the texts give them, and write numbers in digits.
- Attribute every claim and opinion to the outlet or person who makes it. A story told by a blog about another \
outlet's report says so. Never present an allegation as proven.
- Plain sentences that are easy to say aloud. No lists, headings, links, brackets or emoji. Do not mention "the texts"."""

BRIEF_ANSWER = {
    "type": "object",
    "properties": {"opening": {"type": "string"},
                   "items": {"type": "array", "items": {"type": "object", "properties": {
                       "title": {"type": "string"}, "text": {"type": "string"}},
                       "required": ["title", "text"], "additionalProperties": False}}},
    "required": ["opening", "items"],
    "additionalProperties": False,
}


def material(conn, story_ids: list[int]) -> list[dict]:
    stories = []
    for story_id in story_ids:
        title = conn.execute(text("select title from stories where id = :s"), {"s": story_id}).scalar()
        rows = conn.execute(text("""
            select i.source, i.title, i.summary, a.text from story_items si join items i on i.id = si.item_id
            left join articles a on a.item_id = i.id and a.status = 'ok' where si.story_id = :s"""), {"s": story_id}).all()
        body = "\n\n".join(f"Source: {r.source}\nTitle: {r.title}\n{' '.join((r.text or r.summary or '').split()[:SOURCE_WORDS])}" for r in rows)
        stories.append({"id": story_id, "title": title, "text": body})
    return stories


def story_block(stories: list[dict]) -> str:
    return "\n\n".join(f"===== Story {n}: {s['title']} =====\n{s['text']}" for n, s in enumerate(stories, 1))


def main(day: date, story_ids: list[int]) -> None:
    config = settings.load()
    show = config["formats"]["show_name"]
    with db.connect(settings.database_url()).connect() as conn:
        stories = material(conn, story_ids)
    pool = Pool.of([s["text"] for s in stories])
    cost = 0.0

    brief = model.ask(config["model"], BRIEF_RULES, story_block(stories), BRIEF_ANSWER)
    cost += brief.cost

    rules = prompts.PODCAST_RULES + "\n\n" + prompts.KIND_RULES["stories"]
    answer = prompts.segment_answer(("PRESENTER",))
    segments, before = [], "It is what that review publishes and whether anyone outside the police gets to check it."
    for n, (picked, words) in enumerate(SEGMENTS, 1):
        chosen = [stories[i] for i in picked]
        lead = ("This is the first of three segments of smaller stories from today that did not make the main list; "
                "open by saying so in one sentence. " if n == 1 else "")
        message = (f"Show: {show}\n\nYou are writing segment {n} of {len(SEGMENTS)} of extra stories, told after the "
                   f"day's main stories.\nThe segment before yours ended: \"{before}\"\n{lead}\n\n"
                   f"Stories to tell, in this order:\n\n{story_block(chosen)}")
        reply = model.ask(config["model"], rules.format(show=show, words=words), message, answer)
        cost += reply.cost
        lines = [line["text"] for line in reply.data["lines"]]
        segments.append({"stories": [s["id"] for s in chosen], "lines": lines, "illustrations": reply.data["illustrations"]})
        before = lines[-1] if lines else before

    def flags(texts):
        return [(s, p) for t in texts for s in sentences(t) if (p := unsupported(s, pool))]

    brief_texts = [brief.data["opening"]] + [i["text"] for i in brief.data["items"]]
    pod_texts = [line for seg in segments for line in seg["lines"]]
    bw, pw = sum(len(t.split()) for t in brief_texts), sum(len(t.split()) for t in pod_texts)
    md = [f"# Extra stories for {day}", "", f"Briefing {bw} words (about {bw / 146:.1f} min), podcast {pw} words "
          f"(about {pw / 173:.1f} min). Model cost ${cost:.4f}.", "", "## Briefing", "", brief.data["opening"], ""]
    for item in brief.data["items"]:
        md += [f"**{item['title']}**", "", item["text"], ""]
    md += ["## Podcast", ""]
    for n, seg in enumerate(segments, 1):
        md += [f"### Segment {n}", ""] + [line + "\n" for line in seg["lines"]]
        md += ["Writer's own examples: " + " | ".join(seg["illustrations"]), ""] if seg["illustrations"] else []
    md += ["## Fact check", ""]
    found = flags(brief_texts) + flags(pod_texts)
    md += [f"- \"{s}\": {', '.join(p)}" for s, p in found] or ["Every sentence is supported."]
    (HERE / f"extra-{day}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (HERE / f"extra-{day}.json").write_text(json.dumps({"brief": brief.data, "segments": segments}, indent=1), encoding="utf-8")
    print(f"briefing {bw} words, podcast {pw} words, {len(found)} flagged, ${cost:.4f}")


if __name__ == "__main__":
    main(date.fromisoformat(sys.argv[1]), [int(x) for x in sys.argv[2:]])
