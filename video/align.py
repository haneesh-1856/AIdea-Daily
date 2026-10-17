"""Time every spoken word of one day's episode.mp3 with the local Whisper model, so the video follows the voice.

The clip lengths step 10 stored add up to more than the joined episode (2.96 s more on 2026-10-16), so a timeline
built from them drifts behind the audio. This reads the audio itself. Run it with the voice environment:

    .venv-voice\\Scripts\\python.exe video\\align.py 2026-10-16
"""

import json
import sys
from pathlib import Path

import torch  # noqa: F401  loaded before faster_whisper, or CUDA cannot find cublas
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent.parent


def main(day: str) -> None:
    mp3 = ROOT / "out" / day / "episode.mp3"
    target = Path(__file__).parent / "cache" / day / "words.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    model = WhisperModel("medium.en", device="cuda", compute_type="float16")
    # Not conditioned on earlier text: on long files that makes Whisper skip lines.
    segments, info = model.transcribe(str(mp3), word_timestamps=True, condition_on_previous_text=False, beam_size=5, language="en")
    words = []
    for segment in segments:
        for w in segment.words or []:
            words.append({"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})
    target.write_text(json.dumps({"duration": round(info.duration, 3), "words": words}), encoding="utf-8")
    print(f"{len(words)} words timed over {info.duration / 60:.2f} minutes -> {target}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-10-16")
