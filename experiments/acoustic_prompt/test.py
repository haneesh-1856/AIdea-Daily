"""A one-off test, not part of the run: today's stories written with the owner's "acoustic" prompt instead of the
podcast rules. The prompt is in prompt.md, used as given; only its three placeholders are filled in. The stories and
their source text go in the message, as step 8 gives them. The script is written to runs/<date>/prompt-test/.

    .\\.venv\\Scripts\\python.exe -m experiments.acoustic_prompt.test 2026-10-28
"""

import sys
from datetime import date
from pathlib import Path

import anthropic

from common import db, episodes, model, runlog, selections
from common.settings import ROOT, database_url
from common.text import word_count
from steps.step08_write.step import spoken_date, story_message

HERE = Path(__file__).resolve().parent
PERSONA = "sharp, curious and warm: an informed person explaining the day's AI news to a friend"
MAX_TOKENS = 32000


def main(day: date) -> None:
    engine = db.connect(database_url(ROOT))
    with engine.begin() as conn:
        run = runlog.latest_run(conn, day)
        if run is None:
            sys.exit(f"There is no run for {day}.")
        settings = {**run.settings, "model": model.chosen(run.settings, ROOT)}
        lineup = sorted(episodes.lineup(conn, run.id), key=lambda entry: entry.rank)
        parts = [f"Date: {spoken_date(day)}", "", f"Today's {len(lineup)} stories, most important first, with their sources:"]
        for number, entry in enumerate(lineup, 1):
            sources = selections.sources(conn, entry.item_ids)
            earlier = selections.earlier_reports(conn, entry.story_id, entry.thread_id, run.run_date)
            parts += ["", f"===== Story {number} of {len(lineup)} =====", story_message(entry, sources, earlier, settings["write"]["max_source_words"])]

    system = (HERE / "prompt.md").read_text(encoding="utf-8").format(
        topic=f"Today's artificial intelligence news, {spoken_date(day)}: the {len(lineup)} stories in the message",
        persona=PERSONA, guest="Solo Show")
    chosen = settings["model"]
    with anthropic.Anthropic().messages.stream(model=chosen["name"], max_tokens=MAX_TOKENS, system=system,
                                               messages=[{"role": "user", "content": "\n".join(parts)}]) as stream:
        response = stream.get_final_message()
    text = "".join(block.text for block in response.content if block.type == "text")
    cost = (response.usage.input_tokens * chosen.get("price_in", 0) + response.usage.output_tokens * chosen.get("price_out", 0)) / 1_000_000

    folder = ROOT / "runs" / day.isoformat() / "prompt-test"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "acoustic-script.md").write_text(text, encoding="utf-8")
    (folder / "message.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"{word_count(text)} words, stop: {response.stop_reason}, {response.usage.input_tokens} in, "
          f"{response.usage.output_tokens} out, ${cost:.2f}, model {response.model}")
    print(folder / "acoustic-script.md")


if __name__ == "__main__":
    main(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today())
