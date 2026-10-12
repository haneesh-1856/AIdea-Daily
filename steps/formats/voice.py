"""Steps 10 and 11 for the longer episodes: speak each script piece by piece, then join the pieces into an episode."""

import hashlib
import re
import time
from pathlib import Path

import numpy
import soundfile

from common import formats
from steps.step10_voice.step import VoiceError, problem_with, spoken

REACTION_TEMPERATURE = 1.0  # a reaction is given more freedom, so that it is not said flatly
REACTION_GAIN = 1.25  # and is a little louder than the lines around it (about 2 decibels)


def say(text: str, corrections: dict | None) -> str:
    """A piece as the voice model is given it: said aloud by step 10's rules, with its expression tags in front."""
    tags = formats.TAG.findall(text)
    words = re.sub(r"[“”]", '"', formats.plain(text)).replace("’", "'")
    return " ".join([*tags, spoken(words, corrections)])


def prepared(root: Path, name: str, segments: list, chosen: dict, corrections: dict | None) -> list[dict]:
    """The script's pieces with what the voice needs for each: the text to say, whose voice, and a key.

    The key names a clip by its voice and its words, so that a run stopped partway, or repeated, speaks only what
    is missing."""
    found = formats.pieces(segments)
    for piece in found:
        reference = chosen["voices"][formats.VOICES[piece["speaker"]]]
        piece["say"] = say(piece["text"], corrections)
        piece["reference"] = str(root / reference)
        piece["key"] = hashlib.sha1(f"{reference}|{piece['say']}".encode()).hexdigest()[:16]
    return found


def voice_formats(engine, root: Path, run, voice: dict, speak, folder: Path) -> list[str]:
    """Speak every finished longer script. Returns what to add to step 10's summary.

    A script that cannot be spoken is reported and left without audio: the regular episode does not depend on it.
    """
    said = []
    for name in formats.wanted(run.settings):
        about = formats.FORMATS[name]
        with engine.begin() as conn:
            row = formats.scripts_of(conn, run.id).get(name)
            segments = formats.segments_of(conn, run.id, name)
        if row is None or not formats.written(segments):
            continue
        chosen = run.settings["formats"]
        pieces = prepared(root, name, segments, chosen, voice.get("say"))
        missing = sorted({piece["reference"] for piece in pieces if not Path(piece["reference"]).exists()})
        if missing:
            with engine.begin() as conn:
                formats.update(conn, run.id, name, note=f"not spoken: the reference recording is missing: {missing[0]}")
            said.append(f"{about['name']} not spoken")
            continue

        have = {key: clip for key, clip in (row.clips or {}).items() if Path(clip["file"]).exists()}
        clip_folder = folder / f"clips-{name}"
        # Clips are numbered on from the ones already there, so that a repeat never writes over an earlier try's.
        taken = max((int(file.stem) for file in clip_folder.glob("*.wav") if file.stem.isdigit()), default=0)
        wanted, numbers = [], {}
        for piece in pieces:
            if piece["key"] in have or piece["key"] in numbers:
                continue
            numbers[piece["key"]] = taken + len(numbers) + 1
            wanted.append({
                "id": numbers[piece["key"]], "position": numbers[piece["key"]], "text": piece["say"], "phrases": [piece["say"]],
                "reference": piece["reference"], "plain": formats.plain(piece["text"]),
                "temperature": REACTION_TEMPERATURE if piece["reaction"] else voice["temperature"],
            })
        began = time.monotonic()
        failed = []
        try:
            made = speak(wanted, voice, clip_folder) if wanted else {}
            # A failed clip is tried once more, as in the regular episode.
            again = [item for item in wanted if problem_with(made.get(item["id"]), item["plain"])]
            if again:
                made.update(speak(again, voice, clip_folder))
            failed = [(item, problem_with(made.get(item["id"]), item["plain"])) for item in again]
            failed = [(item, problem) for item, problem in failed if problem]
            note = f"not spoken: {len(failed)} pieces failed twice. The first: \"{failed[0][0]['text']}\" ({failed[0][1]})" if failed else None
        except VoiceError as exc:
            made, note = {}, f"not spoken: {exc}"
        unspoken = {item["id"] for item, _ in failed}
        by_number = {number: key for key, number in numbers.items()}
        for number, clip in made.items():
            if number not in unspoken and "file" in clip:
                have[by_number[number]] = {"file": clip["file"], "seconds": clip["seconds"]}
        with engine.begin() as conn:
            # Every good clip is recorded, also when some failed, so that a repeat speaks only what is missing.
            formats.update(conn, run.id, name, clips=have, note=note, voice_seconds=(row.voice_seconds or 0) + time.monotonic() - began)
        said.append(f"{about['name']} not spoken" if note else f"{about['name']} {len(pieces)} pieces spoken")
    return said


def join_formats(conn, root: Path, run, folder: Path) -> list[str]:
    """Join each spoken script into its episode file. Returns what to add to step 11's summary."""
    said = []
    for name in formats.wanted(run.settings):
        about = formats.FORMATS[name]
        row = formats.scripts_of(conn, run.id).get(name)
        segments = formats.segments_of(conn, run.id, name)
        if row is None or not formats.written(segments) or not row.clips:
            continue
        chosen = run.settings["formats"]
        pieces = prepared(root, name, segments, chosen, (run.settings.get("voice") or {}).get("say"))
        if any(piece["key"] not in row.clips or not Path(row.clips[piece["key"]]["file"]).exists() for piece in pieces):
            continue  # step 10 could not speak all of it, and said so
        seconds = join(pieces, row.clips, chosen["pauses"], folder / about["audio"])
        formats.update(conn, run.id, name, audio_seconds=seconds, clips=None)
        # The clips are deleted once the episode file exists.
        for clip in row.clips.values():
            Path(clip["file"]).unlink(missing_ok=True)
        clip_folder = folder / f"clips-{name}"
        if clip_folder.exists() and not any(clip_folder.iterdir()):
            clip_folder.rmdir()
        said.append(f"a {about['name']} episode of {seconds / 60:.1f} minutes")
    return said


def gap_after(piece: dict, following: dict | None, pauses: dict) -> float:
    """How long to stay silent after a piece. A conversation moves faster than a narrator reading alone."""
    if following is None:
        return 0.0
    if following["opens_segment"]:
        return pauses["segment"]
    if following["turn"] == piece["turn"]:
        return pauses["sentence"]
    if following["speaker"] == piece["speaker"]:
        return pauses["paragraph"]
    # A reaction comes in quickly, and so does the answer to one.
    return pauses["reaction"] if piece["reaction"] or following["reaction"] else pauses["turn"]


def join(pieces: list[dict], clips: dict, pauses: dict, target: Path) -> float:
    """Join the clips in order into one MP3, with the voices at the same loudness. Returns its length in seconds."""
    audio, rate = {}, None
    for key in {piece["key"] for piece in pieces}:
        audio[key], clip_rate = soundfile.read(clips[key]["file"], dtype="float32")
        rate = rate or clip_rate
    # The voices are brought to the same loudness, so that one speaker is not quieter than the other.
    level = {}
    for speaker in {piece["speaker"] for piece in pieces}:
        heard = numpy.concatenate([audio[piece["key"]] for piece in pieces if piece["speaker"] == speaker])
        level[speaker] = float(numpy.sqrt(numpy.mean(heard ** 2))) or 1.0
    quietest = min(level.values())
    whole = []
    for number, piece in enumerate(pieces):
        clip = audio[piece["key"]] * (quietest / level[piece["speaker"]]) * (REACTION_GAIN if piece["reaction"] else 1.0)
        following = pieces[number + 1] if number + 1 < len(pieces) else None
        whole += [numpy.clip(clip, -0.98, 0.98), numpy.zeros(int(rate * gap_after(piece, following, pauses)), dtype="float32")]
    episode = numpy.concatenate(whole)
    soundfile.write(target, episode, rate, format="MP3")
    return len(episode) / rate
