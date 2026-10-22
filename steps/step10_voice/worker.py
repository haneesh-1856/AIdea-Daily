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

# A take is spoken again when it pauses longer than this mid-sentence, or is this much louder than the voice's usual
# take: on 2026-10-21 the owner's voice paused 2 to 20 seconds in 24 of 232 sentences and came back shouting, and once
# left out the end of the sentence.
LOUDER_BY = 4.0       # dB above the median of the voice's earlier takes
USUAL_AFTER = 8       # takes heard before the voice's usual loudness is trusted


def levels(audio, rate: int, step: float = 0.01):
    """Loudness in dB of each `step` seconds of the audio."""
    import numpy

    hop = int(rate * step)
    frames = audio[: len(audio) // hop * hop].reshape(-1, hop)
    return 20 * numpy.log10(numpy.sqrt((frames**2).mean(axis=1)) + 1e-9)


def loudness(audio, rate: int) -> float:
    """How loud the take's loudest speech is: the 95th percentile of its half seconds that are not silent."""
    import numpy

    half = levels(audio, rate, 0.5)
    speech = half[half > -40]
    return float(numpy.percentile(speech, 95)) if len(speech) else -99.0


def longest_pause(audio, rate: int) -> float:
    """The longest silence in seconds, counted from the first sound to the last."""
    db = levels(audio, rate)
    silent = db < db.max() - 40
    sound = [i for i, quiet in enumerate(silent) if not quiet]
    longest = run = 0
    for quiet in silent[sound[0]:sound[-1]] if sound else []:
        run = run + 1 if quiet else 0
        longest = max(longest, run)
    return longest * 0.01


def clean(audio, rate: int, breath_below: float = 18.0, shortest: float = 0.2, longest: float = 0.5, edge: float = 0.05):
    """Silence breaths and hiss, then shorten long silences.

    Any stretch of `shortest` seconds or more that stays `breath_below` dB under the loudest speech is a breath or
    a pause, and is made silent with short fades. A silence inside the take is then cut to `longest` seconds, and one
    at its start or end to `edge`, since step 10 sets the pause between sentences itself.
    """
    import numpy

    hop = int(rate * 0.01)
    audio = audio[: len(audio) // hop * hop].copy()
    db = levels(audio, rate)
    top = numpy.percentile(db, 95)

    def stretches(mask):
        i, n = 0, len(mask)
        while i < n:
            j = i
            while j < n and mask[j] == mask[i]:
                j += 1
            yield i, j, bool(mask[i])
            i = j

    fade = int(rate * 0.015)
    for i, j, quiet in stretches(db < top - breath_below):
        if quiet and (j - i) * 0.01 >= shortest:
            s, e = i * hop, j * hop
            gain = numpy.zeros(e - s, dtype="float32")
            gain[: min(fade, e - s)] = numpy.linspace(1, 0, min(fade, e - s))
            gain[max(0, e - s - fade):] = numpy.linspace(0, 1, e - s - max(0, e - s - fade))
            audio[s:e] *= gain

    db = levels(audio, rate)
    keep, last = [], len(db)
    for i, j, quiet in stretches(db < top - 40):
        piece = audio[i * hop:j * hop]
        if quiet:
            most = int(rate * (edge if i == 0 or j == last else longest))
            if len(piece) > most:
                piece = numpy.concatenate([piece[: most // 2], piece[len(piece) - (most - most // 2):]])
        keep.append(piece)
    return numpy.concatenate(keep).astype("float32")


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

    turbo = job["engine"] == "chatterbox-turbo"
    if turbo:
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        model = ChatterboxTurboTTS.from_pretrained(device=device)
    else:
        from chatterbox.tts import ChatterboxTTS

        model = ChatterboxTTS.from_pretrained(device=device)
    using = None

    def use(reference: str) -> None:
        """A reference voice is worked out once and used for every sentence that follows in it."""
        nonlocal using
        if reference != using:
            model.prepare_conditionals(reference, **({} if turbo else {"exaggeration": job["exaggeration"]}))
            using = reference

    def say(phrase: str, temperature: float):
        options = {"temperature": temperature} if turbo else {"temperature": temperature, "exaggeration": job["exaggeration"], "cfg_weight": job["cfg_weight"]}
        audio = model.generate(phrase, **options).squeeze().cpu().numpy()
        if job["speed"] != 1.0:
            # Faster or slower without changing the pitch. This method keeps speech clean for changes of this size.
            audio = pytsmod.wsola(audio.astype("float64"), 1 / job["speed"]).astype("float32")
        return audio

    retakes, pause_limit = job.get("retakes", 0), job.get("longest_pause", 2.0)
    usual: dict[str, list[float]] = {}  # each voice's loudness, take by take

    def trouble(audio, voice: str) -> float:
        """How far a take is from a calm, whole one: 0 is fine."""
        heard = usual.setdefault(voice, [])
        louder = loudness(audio, model.sr) - (float(numpy.median(heard)) if len(heard) >= USUAL_AFTER else 99.0)
        return max(0.0, longest_pause(audio, model.sr) - pause_limit) + max(0.0, louder - LOUDER_BY) / LOUDER_BY

    results = {}
    result_file = Path(job_file).with_name("result.json")
    # A sentence may name its own voice and delivery: an episode with two speakers does. All of one voice's
    # sentences are spoken before the next voice's, so that each voice is worked out once.
    for item in sorted(job["sentences"], key=lambda item: item.get("reference") or job["reference"]):
        try:
            voice = item.get("reference") or job["reference"]
            use(voice)
            takes = []
            for _ in range(1 + retakes):
                # A long sentence arrives as phrases: each is spoken on its own and a short silence is left between them.
                spoken = [say(phrase, item.get("temperature", job["temperature"])) for phrase in item["phrases"]]
                gap = numpy.zeros(int(model.sr * job["phrase_pause"]), dtype="float32")
                audio = numpy.concatenate([piece for phrase in spoken for piece in (phrase, gap)][:-1])
                takes.append((trouble(audio, voice) if retakes else 0.0, len(takes), audio))
                if takes[-1][0] == 0:
                    break
            # The calmest take is kept. Only a fine one counts towards the voice's usual loudness.
            fault, _, audio = min(takes, key=lambda take: take[:2])
            if retakes and fault == 0:
                usual[voice].append(loudness(audio, model.sr))
            if job.get("clean"):
                audio = clean(audio, model.sr)
            file = folder / f"{item['position']:04d}.wav"
            soundfile.write(file, audio, model.sr)
            results[str(item["id"])] = {"file": str(file), "seconds": len(audio) / model.sr, "takes": len(takes)}
        except Exception as exc:  # one bad sentence is reported, and the rest are still spoken
            results[str(item["id"])] = {"error": f"{type(exc).__name__}: {exc}"}
        # Written after every sentence, so that a run stopped partway keeps what it has made.
        result_file.write_text(json.dumps({"device": device, "clips": results}), encoding="utf-8")

    result_file.write_text(json.dumps({"device": device, "clips": results, "finished": True}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
