"""Writes down what each clip says, with Whisper. Run by step 10 with the voice environment's Python, not the pipeline's:

    .venv-voice/Scripts/python.exe steps/step10_voice/listener.py job.json

The job file lists the clips and the Whisper model. The answer is written back beside it as heard.json: each clip's
id with the words Whisper heard. Like worker.py, this file imports nothing from the rest of the project.
"""

import json
import logging
import sys
import warnings
from pathlib import Path


def main(job_file: str) -> int:
    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    import torch  # loaded before faster_whisper, or CUDA cannot find cublas64_12.dll

    from faster_whisper import WhisperModel

    job = json.loads(Path(job_file).read_text(encoding="utf-8"))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = WhisperModel(job["model"], device=device, compute_type="float16" if device == "cuda" else "int8")
    heard = {}
    answer = Path(job_file).with_name("heard.json")
    for clip in job["clips"]:
        try:
            # Not conditioned on earlier text and without voice detection: each clip is one sentence, and every
            # word of it should be written down, even a quiet one.
            segments, _ = model.transcribe(clip["file"], language="en", beam_size=5, condition_on_previous_text=False)
            heard[str(clip["id"])] = {"text": " ".join(segment.text.strip() for segment in segments)}
        except Exception as exc:  # one unreadable clip is reported, and the rest are still heard
            heard[str(clip["id"])] = {"error": f"{type(exc).__name__}: {exc}"}
    answer.write_text(json.dumps({"device": device, "heard": heard, "finished": True}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
