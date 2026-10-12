"""A test, not part of the daily run: speaks a host-and-guest script in two voices with Chatterbox Turbo.

Run it with the voice environment's Python, from the project folder:

    .venv-voice/Scripts/python.exe voice/two_voice_test.py SCRIPT.md HOST_REFERENCE GUEST_REFERENCE OUT_FOLDER [--turns N]

The script is the Markdown the two-voice episode is written in: a spoken line starts with **HOST:** or **GUEST:**,
and everything else (headings, notes that begin with ">") is not spoken. A word in square brackets at the start
of a sentence, such as [surprised] or [laugh], is one of the model's own expression tags and is passed to it.

Like the worker of step 10, this file imports nothing from the rest of the project, because the two environments
have different libraries installed. The rules for how text is said aloud are copied from step 10.

A VOICE COPIED FROM A REAL PERSON WHO HAS NOT AGREED TO IT IS FOR PRIVATE TESTING ONLY. The episode this writes is
named as a test for that reason, and must not be published or shared.
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import time
import warnings
from pathlib import Path

LINE = re.compile(r"\*\*(HOST|GUEST):\*\*\s*(.+)")
TAG = re.compile(r"\[(?:advertisement|angry|chuckle|clear throat|cough|crying|dramatic|fear|gasp|groan|happy|laugh|narration|"
                 r"sarcastic|shush|sigh|sniff|surprised|whispering)\]")
SCALES = {"k": "thousand", "m": "million", "b": "billion", "t": "trillion"}
SLOWEST, FASTEST = 0.8, 7.0  # words a second: outside this a clip is not believable, as in step 10
TEMPERATURE, REACTION_TEMPERATURE = 0.8, 1.0  # a reaction is given more freedom, so that it is not said flatly
REACTION_GAIN = 1.25  # and is a little louder than the lines around it (about 2 decibels)
# Seconds of silence, by what comes next. A conversation moves faster than a narrator reading alone.
PAUSE_SENTENCE, PAUSE_TURN, PAUSE_AFTER_REACTION, PAUSE_SEGMENT = 0.32, 0.38, 0.22, 1.1
MIN_WORDS = 4  # the model is unsteady on a shorter piece, so a short sentence is said together with its neighbour


def spaced(word: str) -> str:
    """SynthID -> Synth-ID, OpenAI -> Open-AI: the voice runs such a word together without the hyphen."""
    if not re.search(r"[a-z][A-Z]", word) or re.match(r"Ma?c[A-Z]", word):
        return word
    return "-".join(re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+", word))


def spoken(text: str) -> str:
    """The sentence as it should be said aloud, by step 10's rules. Expression tags are kept as they are."""
    tags = TAG.findall(text)
    text = TAG.sub(" ", text)
    text = re.sub(r"[*`_]", "", text).replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(
        r"\$(\d[\d,]*(?:\.\d+)?)(?:\s*(thousand|million|billion|trillion)\b|([KkMmBbTt])\b)?",
        lambda m: f"{m.group(1)} {m.group(2) or SCALES.get((m.group(3) or '').lower(), '')} dollars".replace("  ", " "), text,
    )
    text = re.sub(r"(\d)\s?%", r"\1 percent", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)x\b", r"\1 times", text)
    text = text.replace(" & ", " and ").replace("~", "about ")
    text = re.sub(r"[\[\]]", "", text)
    text = re.sub(r"[A-Za-z]+", lambda m: spaced(m.group()), text)
    text = re.sub(r"\s+", " ", text).strip()
    return (" ".join(tags) + " " + text).strip()


def sentences(text: str) -> list[str]:
    """A turn split into the pieces spoken one at a time. A piece of under MIN_WORDS words joins the one before it,
    or the one after it when it opens the turn."""
    parts = [part.strip() for part in re.split(r"(?<=[.!?])[\"']?\s+(?=[\"'\[]?[A-Z0-9\[])", text.strip()) if part.strip()]
    merged: list[str] = []
    for part in parts:
        short = len(TAG.sub("", part).split()) < MIN_WORDS
        # "the U.S. Department" was split above; an ending like that is glued back to what follows.
        if merged and (short or re.search(r"\b(?:[A-Z]\.|Mr\.|Dr\.|vs\.)$", merged[-1]) or len(TAG.sub("", merged[-1]).split()) < MIN_WORDS):
            merged[-1] += " " + part
        else:
            merged.append(part)
    return merged


def read_script(path: Path, turns: int | None) -> list[dict]:
    """Every piece to speak, in order: who says it, the text, whether it is a reaction, and what kind of gap follows."""
    found, new_segment, turn = [], False, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Runtime"):
            break
        if line.startswith("## "):
            new_segment = True
            continue
        match = LINE.match(line)
        if not match:
            continue
        turn += 1
        if turns and turn > turns:
            break
        who, said = match.groups()
        for place, piece in enumerate(sentences(said)):
            found.append({
                "who": who, "turn": turn, "text": piece, "say": spoken(piece),
                # A reaction is a piece the script gave an expression tag, or one that is exclaimed.
                "reaction": bool(TAG.search(piece)) or piece.rstrip("\"'").endswith(("!", "?!")),
                "opens_segment": new_segment and place == 0,
            })
        new_segment = False
    return found


def believable(seconds: float, text: str) -> bool:
    words = len(TAG.sub("", text).split())
    return seconds > 0 and (words < 4 or SLOWEST <= words / seconds <= FASTEST)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path)
    parser.add_argument("host", type=Path)
    parser.add_argument("guest", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--turns", type=int, help="speak only the first N turns, to try it out")
    args = parser.parse_args()

    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    import numpy
    import soundfile
    import torch
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    pieces = read_script(args.script, args.turns)
    clips = args.out / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ChatterboxTurboTTS.from_pretrained(device=device)
    started, made, failed = time.time(), 0, []

    # Each voice is worked out once, and all of that speaker's lines are spoken before the other's.
    for who, reference in (("HOST", args.host), ("GUEST", args.guest)):
        model.prepare_conditionals(str(reference))
        for number, piece in enumerate(pieces):
            if piece["who"] != who:
                continue
            # A clip is named by its place and its words, so a run stopped partway, or a script changed in a few
            # places, speaks only what is missing.
            mark = hashlib.sha1(f"{who}|{reference.name}|{piece['say']}".encode()).hexdigest()[:10]
            piece["file"] = clips / f"{number:04d}-{who.lower()}-{mark}.wav"
            if piece["file"].exists():
                continue
            temperature = REACTION_TEMPERATURE if piece["reaction"] else TEMPERATURE
            for attempt in (1, 2):  # a clip of an unbelievable length is spoken once more
                audio = model.generate(piece["say"], temperature=temperature).squeeze().cpu().numpy()
                if believable(len(audio) / model.sr, piece["text"]):
                    break
            else:
                failed.append(f"{number}: {piece['text'][:60]}")
            soundfile.write(piece["file"], audio, model.sr)
            made += 1
            if made % 25 == 0:
                print(f"{made} clips spoken, {time.time() - started:.0f} seconds", flush=True)

    # The two voices are brought to the same loudness, so that one speaker is not quieter than the other.
    audio = {number: soundfile.read(piece["file"], dtype="float32")[0] for number, piece in enumerate(pieces)}
    level = {who: float(numpy.sqrt(numpy.mean(numpy.concatenate([audio[n] for n, p in enumerate(pieces) if p["who"] == who]) ** 2)))
             for who in ("HOST", "GUEST") if any(p["who"] == who for p in pieces)}
    target = min(level.values())
    whole, seconds = [], {"HOST": 0.0, "GUEST": 0.0}
    for number, piece in enumerate(pieces):
        clip = audio[number] * (target / level[piece["who"]]) * (REACTION_GAIN if piece["reaction"] else 1.0)
        clip = numpy.clip(clip, -0.98, 0.98)
        seconds[piece["who"]] += len(clip) / model.sr
        following = pieces[number + 1] if number + 1 < len(pieces) else None
        if following is None:
            gap = 0.0
        elif following["opens_segment"]:
            gap = PAUSE_SEGMENT
        elif following["turn"] == piece["turn"]:
            gap = PAUSE_SENTENCE
        else:
            # A reaction comes in quickly, and so does the answer to one.
            gap = PAUSE_AFTER_REACTION if piece["reaction"] or following["reaction"] else PAUSE_TURN
        whole += [clip, numpy.zeros(int(model.sr * gap), dtype="float32")]
    episode = numpy.concatenate(whole)
    name = "TEST ONLY - not for publishing - two-voice episode" + (f" (first {args.turns} turns)" if args.turns else "")
    target_file = args.out / f"{name}.mp3"
    soundfile.write(target_file, episode, model.sr, format="MP3")
    result = {
        "file": str(target_file), "minutes": round(len(episode) / model.sr / 60, 1), "pieces": len(pieces),
        "reactions": sum(piece["reaction"] for piece in pieces), "spoken_now": made, "device": device,
        "host_minutes": round(seconds["HOST"] / 60, 1), "guest_minutes": round(seconds["GUEST"] / 60, 1),
        "made_in_minutes": round((time.time() - started) / 60, 1), "unbelievable_lengths": failed,
        "host_reference": str(args.host), "guest_reference": str(args.guest),
    }
    (args.out / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
