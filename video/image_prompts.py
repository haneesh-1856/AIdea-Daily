"""Ask the language model for two picture descriptions per story, for make_images.py to draw.

The pictures illustrate a story's idea; they never show logos, text or real people, which an image model gets wrong.
One request covers the whole episode and costs a few cents.

    .venv\\Scripts\\python.exe video\\image_prompts.py 2026-10-16
"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common import model  # noqa: E402
from common.settings import load  # noqa: E402

PER_STORY = 2
SYSTEM = f"""You write prompts for an image model (SDXL-Turbo) that makes b-roll for a daily AI news video.
For each story, write {PER_STORY} different prompts of 25 to 45 words. Each describes one concrete, photographic or
cinematic scene that suits the story: hardware, people at work seen from behind or out of focus, places, objects,
abstract data. Never ask for text, letters, numbers, logos, brand names, user interfaces with words, or a real,
named person; the model draws those badly. Name the lighting and lens. The video's look is near-black with a
signal-red accent, so ask for dark, moody scenes with some red light."""
SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"story": {"type": "integer"}, "prompts": {"type": "array", "items": {"type": "string"}}},
                "required": ["story", "prompts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["stories"],
    "additionalProperties": False,
}


def main(day: str) -> None:
    conn = sqlite3.connect(ROOT / "data" / "local.db")
    run_id = conn.execute("select id from runs where run_date=? order by id desc limit 1", (day,)).fetchone()[0]
    rows = conn.execute(
        """select l.story_id, l.part, l.text from clips k join script_lines l on l.id = k.line_id
           where k.run_id = ? and l.story_id is not null and l.part in ('title', 'what', 'brief') order by k.position""",
        (run_id,),
    ).fetchall()
    stories: dict[int, list[str]] = {}
    for story_id, part, text in rows:
        stories.setdefault(story_id, []).append(text)
    material = "\n\n".join(f"Story {story_id}:\n" + " ".join(lines[:4]) for story_id, lines in stories.items())
    reply = model.ask(load(ROOT)["model"], SYSTEM, material, SCHEMA)
    prompts = {str(s["story"]): s["prompts"][:PER_STORY] for s in reply.data["stories"] if s["story"] in stories}
    target = Path(__file__).parent / "cache" / day / "image-prompts.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(prompts, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{sum(len(p) for p in prompts.values())} prompts for {len(prompts)} stories, ${reply.cost:.4f} -> {target}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-10-16")
