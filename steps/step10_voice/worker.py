"""Speaks sentences with Chatterbox. Run by step 10 with the voice environment's Python, not the pipeline's:

    .venv-voice/Scripts/python.exe steps/step10_voice/worker.py job.json

The job file lists the sentences, the reference recording, the settings and where to put the clips. The answer is
written back beside it as result.json. This file imports nothing from the rest of the project, because the two
environments have different libraries installed.
"""

import json
import logging
import sys
import warnings
from pathlib import Path


def main(job_file: str) -> int:
    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    import numpy
    import pytsmod
    import soundfile
    import torch

    job = json.loads(Path(job_file).read_text(encoding="utf-8"))
    folder = Path(job["folder"])
    folder.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # The reference voice is worked out once and used for every sentence.
    if job["engine"] == "chatterbox-turbo":
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        model = ChatterboxTurboTTS.from_pretrained(device=device)
        model.prepare_conditionals(job["reference"])
        options = {"temperature": job["temperature"]}
    else:
        from chatterbox.tts import ChatterboxTTS

        model = ChatterboxTTS.from_pretrained(device=device)
        model.prepare_conditionals(job["reference"], exaggeration=job["exaggeration"])
        options = {key: job[key] for key in ("temperature", "exaggeration", "cfg_weight")}

    def say(phrase: str):
        audio = model.generate(phrase, **options).squeeze().cpu().numpy()
        if job["speed"] != 1.0:
            # Faster or slower without changing the pitch. This method keeps speech clean for changes of this size.
            audio = pytsmod.wsola(audio.astype("float64"), 1 / job["speed"]).astype("float32")
        return audio

    results = {}
    result_file = Path(job_file).with_name("result.json")
    for item in job["sentences"]:
        try:
            # A long sentence arrives as phrases: each is spoken on its own and a short silence is left between them.
            spoken = [say(phrase) for phrase in item["phrases"]]
            gap = numpy.zeros(int(model.sr * job["phrase_pause"]), dtype="float32")
            audio = numpy.concatenate([piece for phrase in spoken for piece in (phrase, gap)][:-1])
            file = folder / f"{item['position']:04d}.wav"
            soundfile.write(file, audio, model.sr)
            results[str(item["id"])] = {"file": str(file), "seconds": len(audio) / model.sr}
        except Exception as exc:  # one bad sentence is reported, and the rest are still spoken
            results[str(item["id"])] = {"error": f"{type(exc).__name__}: {exc}"}
        # Written after every sentence, so that a run stopped partway keeps what it has made.
        result_file.write_text(json.dumps({"device": device, "clips": results}), encoding="utf-8")

    result_file.write_text(json.dumps({"device": device, "clips": results, "finished": True}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
