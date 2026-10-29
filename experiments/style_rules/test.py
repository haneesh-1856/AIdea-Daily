"""A one-off test, not part of the run: the day's podcast written again with the owner's style rules (style.md)
added after the podcast rules. It uses the day's saved plan and the same messages as step 8, segment by segment,
and changes nothing in the database. The script is written to runs/<date>/prompt-test/style-script.md, beside the
day's own podcast script copied as podcast-script-before.md for comparison.

    .\\.venv\\Scripts\\python.exe -m experiments.style_rules.test 2026-10-28
"""

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from common import db, episodes, formats, model, runlog, script, selections
from common.settings import ROOT, database_url
from steps.formats import prompts
from steps.formats.write import _Entry, clean_lines, segment_message

HERE = Path(__file__).resolve().parent
NAME = "podcast"


def as_text(plan: list) -> str:
    lines = []
    for segment in plan:
        lines += [f"## {segment.position}. {segment.title}", ""]
        lines += [line["text"] + "\n" for line in segment.lines or []]
    return "\n".join(lines)


def main(day: date) -> None:
    engine = db.connect(database_url(ROOT))
    with engine.begin() as conn:
        run = runlog.latest_run(conn, day)
        if run is None:
            sys.exit(f"There is no run for {day}.")
        settings = {**run.settings, "model": model.chosen(run.settings, ROOT)}
        have = script.summaries_of(conn, run.id)
        ranked = []
        for entry in episodes.lineup(conn, run.id):
            if entry.story_id in have and not have[entry.story_id].flag:
                sources = selections.sources(conn, entry.item_ids)
                earlier = selections.earlier_reports(conn, entry.story_id, entry.thread_id, run.run_date)
                ranked.append(_Entry(entry, (sources, earlier)))
        saved = formats.segments_of(conn, run.id, NAME)
    if not saved:
        sys.exit(f"The run of {day} has no {NAME} plan.")
    by_story = {entry.story_id: entry for entry in ranked}
    show = settings["formats"]["show_name"]

    folder = ROOT / "runs" / day.isoformat() / "prompt-test"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "podcast-script-before.md").write_text(as_text(saved), encoding="utf-8")

    # The same plan, with the lines written afresh.
    plan = [SimpleNamespace(**{key: getattr(row, key) for key in ("position", "kind", "title", "angle", "story_ids", "words")}, lines=None)
            for row in saved]
    style = (HERE / "style.md").read_text(encoding="utf-8")
    cost = 0.0
    for place, segment in enumerate(plan):
        rules = prompts.RULES[NAME].format(show=show, words=segment.words) + "\n\n" + prompts.KIND_RULES[segment.kind] + "\n\n" + style
        message = segment_message(run.run_date, show, plan, segment, plan[place - 1] if place else None, by_story, have,
                                  settings["write"]["max_source_words"])
        reply = model.ask(settings["model"], rules, message, prompts.segment_answer(formats.FORMATS[NAME]["speakers"]))
        segment.lines = clean_lines(reply.data, formats.FORMATS[NAME]["speakers"])
        cost += reply.cost
        print(f"{segment.position}. {segment.title}: {formats.spoken_words(segment.lines)} words")

    (folder / "style-script.md").write_text(as_text(plan), encoding="utf-8")
    print(f"{sum(formats.spoken_words(s.lines) for s in plan)} words in all, before {sum(formats.spoken_words(s.lines) for s in saved)}; ${cost:.2f}")
    print(folder / "style-script.md")


if __name__ == "__main__":
    main(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today())
