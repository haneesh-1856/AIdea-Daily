"""Speaks a sample written by sample.py in the episode's voice, for the owner to hear.

    .venv/Scripts/python.exe -m experiments.weekend_edition.speak 2026-11-01
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from common import settings
from common.text import sentences
from steps.step10_voice.step import run_worker, spoken
from steps.step11_assemble.step import join_clips

HERE = Path(__file__).parent


def main(last: str) -> None:
    config = settings.load()
    voice, pauses = config["voice"], config["voice"]["pauses"]
    answer = json.loads((HERE / f"sample-{last}.json").read_text(encoding="utf-8"))["answer"]
    # The opening, each story's title then its paragraphs, and the closing; a new story gets the longer pause.
    blocks = [[answer["opening"]]] + [[part["title"] + "."] + part["text"].split("\n\n") for part in answer["parts"]] + [[answer["closing"]]]
    lines = []
    for block in blocks:
        for n, paragraph in enumerate(block):
            said = sentences(paragraph)
            for k, sentence in enumerate(said):
                last_in_block = n == len(block) - 1 and k == len(said) - 1
                pause = pauses["story"] if last_in_block else pauses["part"] if k == len(said) - 1 else pauses["sentence"]
                lines.append((sentence, pause))

    items = [{"id": i, "position": i, "text": spoken(s, voice.get("say")), "phrases": [spoken(s, voice.get("say"))]}
             for i, (s, _) in enumerate(lines)]
    clips = run_worker(settings.ROOT)(items, voice, HERE / f"clips-{last}")
    missing = [i for i in range(len(lines)) if "file" not in clips.get(i, {})]
    found = [SimpleNamespace(file=clips[i]["file"], pause_after=pause) for i, (_, pause) in enumerate(lines) if i not in missing]
    seconds = join_clips(found, HERE / f"sample-{last}.mp3")
    print(f"{len(found)} of {len(lines)} sentences spoken, {seconds / 60:.1f} minutes: {HERE / f'sample-{last}.mp3'}")


if __name__ == "__main__":
    main(sys.argv[1])
