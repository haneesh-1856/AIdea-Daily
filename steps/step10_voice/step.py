"""Step 10, Voice: turn the final script into speech, one clip per sentence."""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError

from common import clips, db, episodes, runlog, script
from common.report import step_folder, write_report
from common.settings import ROOT, database_url, load
from common.text import word_count

STEP = 10
WORKER = Path(__file__).with_name("worker.py")
WORKER_LIMIT = 90 * 60  # seconds the voice model may take for one episode
# A clip far too short or far too long for its words means the model slipped: it is spoken again.
SLOWEST, FASTEST = 0.8, 7.0  # words a second
# sentences to speak, the voice settings, the folder for the clips -> {sentence id: {"file", "seconds"} or {"error"}}
Speak = Callable[[list[dict], dict, Path], dict]

SCALES = {"k": "thousand", "m": "million", "b": "billion", "t": "trillion"}
SIZES = {"K": "kilobytes", "M": "megabytes", "G": "gigabytes", "T": "terabytes"}


class VoiceError(Exception):
    """The step could not run, or a sentence could not be spoken. The message says why."""


@dataclass
class VoiceResult:
    run_id: int
    run_date: date
    state: str  # voiced, skipped, already_done
    clips: int
    seconds: float
    report: Path


def spoken(text: str, say: dict[str, str] | None = None) -> str:
    """The sentence as it should be said aloud. This changes how the text is spoken, never what it says."""
    for written, said in (say or {}).items():
        text = re.sub(rf"(?<![\w-]){re.escape(written)}(?![\w-])", said, text)
    # $300 million, $4B, $20 -> 300 million dollars, 4 billion dollars, 20 dollars
    # Before a noun it is "dollar": "a 1.8 billion dollar push". That is the case after a, the, its or a possessive.
    text = re.sub(
        r"(\b(?i:an?|the|its|his|her|their|our)\s+|['’]s\s+)?\$(\d[\d,]*(?:\.\d+)?)(?:\s*(thousand|million|billion|trillion)\b|([KkMmBbTt])\b)?",
        lambda m: (m.group(1) or "")
        + f"{m.group(2)} {m.group(3) or SCALES.get((m.group(4) or '').lower(), '')} {'dollar' if m.group(1) else 'dollars'}".replace("  ", " "),
        text,
    )
    # 501B, 270M, 1T, 8K -> 501 billion, 270 million, 1 trillion, 8 thousand
    text = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)([KMBT])\b", lambda m: f"{m.group(1)} {SCALES[m.group(2).lower()]}", text)
    # 191MB, 8GB -> 191 megabytes, 8 gigabytes
    text = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s?([KMGT])B\b", lambda m: f"{m.group(1)} {SIZES[m.group(2)]}", text)
    # A scale word joined to what follows by a hyphen is said as two words: "501 billion-parameter" stays, but
    # "501 billion-A23B" would be read as one tangle.
    text = re.sub(r"\b(thousand|million|billion|trillion)-(?=[A-Z0-9])", r"\1 ", text)
    text = re.sub(r"(\d)\s?%", r"\1 percent", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)x\b", r"\1 times", text)
    # V4.1, v1.1, DSv4 -> version 4.1, version 1.1, DS version 4
    text = re.sub(r"(?<![A-Za-z])[vV](\d+(?:\.\d+)*)\b", r"version \1", text)
    text = re.sub(r"(?<=[A-Z])v(\d+(?:\.\d+)*)\b", r" version \1", text)
    text = text.replace(" & ", " and ").replace("~", "about ")
    text = re.sub(r"[\[\]]", "", text)
    text = re.sub(r"[A-Za-z]+", lambda m: spaced(m.group()), text)
    return re.sub(r"\s+", " ", text).strip()


def spaced(word: str) -> str:
    """A word that joins a capital onto another word gets a hyphen at the join: SynthID -> Synth-ID,
    OpenAI -> Open-AI, textGrain -> text-Grain.

    The voice runs such a word together; the hyphen makes it say the two parts. A word that is all capitals, an
    ordinary word, and a name such as McCallum are left alone. Only the voice is given this form: the script file,
    the newsletter and the show notes keep the word as written.
    """
    if not re.search(r"[a-z][A-Z]", word) or re.match(r"Ma?c[A-Z]", word):
        return word
    return "-".join(re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+", word))


def phrases(text: str, longest: int) -> list[str]:
    """A long sentence split where a speaker would breathe: at commas, semicolons, colons and dashes.

    Spoken in one go, a long sentence comes out as one flat run. Phrase by phrase, each piece gets its own rise
    and fall and a short pause after it, the way the reference recording is spoken. No piece is under four words.
    """
    if word_count(text) <= longest:
        return [text]
    found: list[str] = []
    for piece in re.split(r"(?<=[,;:—])\s+", text):
        if found and (word_count(found[-1]) < 4 or word_count(found[-1]) + word_count(piece) <= 9):
            found[-1] += " " + piece
        else:
            found.append(piece)
    if len(found) > 1 and word_count(found[-1]) < 4:
        last = found.pop()
        found[-1] += " " + last
    return found


def pause_after(line, following, pauses: dict) -> float:
    """How long to stay silent after a line, from what comes next."""
    if following is None:
        return 0.0
    if line.part == "headline":
        # Between headlines a short beat; after the last one, the stories begin.
        return pauses["headline"] if following.part == "headline" else pauses["story"]
    if line.part == "cue":
        # "Next up." runs on into the title with only a breath between them.
        return pauses["sentence"]
    if line.story_id != following.story_id or (line.story_id is None and line.part != following.part):
        return pauses["story"]
    return pauses["sentence"] if line.part == following.part else pauses["part"]


def run_worker(root: Path) -> Speak:
    """Speaks with the voice model, in its own Python environment."""

    def speak(sentences: list[dict], voice: dict, folder: Path) -> dict:
        python, reference = root / voice["python"], root / voice["reference"]
        for needed, what in ((python, "the voice environment"), (reference, "the reference recording")):
            if not needed.exists():
                raise VoiceError(f"{what} is missing: {needed}")
        folder.mkdir(parents=True, exist_ok=True)
        job = folder / "job.json"
        job.write_text(
            json.dumps({
                "sentences": sentences, "reference": str(reference), "folder": str(folder),
                "phrase_pause": voice["pauses"]["phrase"],
                **{key: voice[key] for key in ("engine", "temperature", "exaggeration", "cfg_weight", "speed")},
            }),
            encoding="utf-8",
        )
        # The model's files are kept inside the project, so nothing is downloaded again and nothing depends on a hidden cache.
        env = dict(os.environ, HF_HOME=str(root / "data" / "models" / "huggingface"))
        result = job.with_name("result.json")
        result.unlink(missing_ok=True)
        try:
            done = subprocess.run([str(python), str(WORKER), str(job)], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=WORKER_LIMIT)
            trouble = (done.stderr or done.stdout).strip()[-800:] if done.returncode != 0 else None
        except subprocess.TimeoutExpired:
            trouble = f"it took longer than {WORKER_LIMIT // 60} minutes and was stopped"
        # The model reports each clip as it makes it. If it stopped partway, what it made is still used: the
        # sentences it did not reach come back as missing, and step 10 treats a missing clip as a failed one.
        if not result.exists():
            raise VoiceError(f"The voice model made nothing: {trouble or 'it gave no answer'}")
        answer = json.loads(result.read_text(encoding="utf-8"))["clips"]
        job.unlink()
        result.unlink()
        return {int(line_id): clip for line_id, clip in answer.items()}

    return speak


def problem_with(clip: dict | None, text: str) -> str | None:
    """Why a clip cannot be used, or None if it can."""
    if clip is None:
        return "no clip came back"
    if "error" in clip:
        return clip["error"]
    words = word_count(text)
    if clip["seconds"] <= 0 or (words >= 4 and not SLOWEST <= words / clip["seconds"] <= FASTEST):
        return f"{clip['seconds']:.1f} seconds is not a believable length for {words} words"
    return None


def voice(run_date: date, *, root: Path = ROOT, speak: Speak | None = None) -> VoiceResult:
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"
    folder = root / "out" / run_date.isoformat() / "clips"

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if 9 not in done:
                raise VoiceError(f"There is no final script for {run_date}. Run step 9 first.")
            if STEP in done:
                found = clips.of_run(conn, run.id)
                return VoiceResult(run.id, run_date, "already_done", len(found), sum(clip.seconds for clip in found), report)

            # A run started before the voice step existed has no voice settings of its own; the file's are used.
            settings = run.settings.get("voice") or load(root)["voice"]
            episode = episodes.get(conn, run.id)
            reason = None
            if not settings["enabled"]:
                reason = "Voice is switched off in settings."
            elif episode.status == "held":
                reason = "The episode is held, so it is not voiced until you have looked at it."
            if reason:
                runlog.skip_step(conn, run.id, STEP, reason)
                write_report(root, run_date, STEP, [f"# Step 10, Voice: {run_date.isoformat()}", "", f"Skipped. {reason}"])
                return VoiceResult(run.id, run_date, "skipped", 0, 0.0, report)

            runlog.begin_step(conn, run.id, STEP)
            lines = [line for line in script.lines_of(conn, run.id) if line.status == "kept"]
            # A clip spoken on an earlier try, whose file is still there, is not spoken again.
            have = {clip.line_id: clip for clip in clips.of_run(conn, run.id) if Path(clip.file).exists()}

        speak = speak or run_worker(root)
        texts = {line.id: spoken(line.text, settings.get("say")) for line in lines}
        longest = settings["pauses"]["longest_phrase"]
        wanted = [
            {"id": line.id, "position": line.position, "text": texts[line.id], "phrases": phrases(texts[line.id], longest)}
            for line in lines if line.id not in have
        ]
        began = time.monotonic()
        made = speak(wanted, settings, folder) if wanted else {}
        # A failed clip is tried once more. If it fails again the run stops, so a broken episode is never produced.
        again = [item for item in wanted if problem_with(made.get(item["id"]), item["text"])]
        if again:
            made.update(speak(again, settings, folder))
        failed = [(item, problem_with(made.get(item["id"]), item["text"])) for item in again]
        failed = [(item, problem) for item, problem in failed if problem]
        took = time.monotonic() - began

        unspoken = {item["id"] for item, _ in failed}
        with engine.begin() as conn:
            # Every good clip is recorded, also when the step is about to fail, so that a rerun speaks only what is missing.
            for index, line in enumerate(lines):
                if line.id in unspoken:
                    continue
                following = lines[index + 1] if index + 1 < len(lines) else None
                clip = made.get(line.id) or {"file": have[line.id].file, "seconds": have[line.id].seconds}
                clips.save(conn, run.id, line.id, line.position, clip["file"], clip["seconds"], pause_after(line, following, settings["pauses"]))
            if failed:
                item, problem = failed[0]
                detail = f"{len(failed)} sentences could not be spoken, even on a second try. The first: \"{item['text']}\" ({problem})"
                runlog.finish_step(conn, run.id, STEP, "failed", detail)
        if failed:
            raise VoiceError(detail)

        with engine.begin() as conn:
            found = clips.of_run(conn, run.id)
            speech = sum(clip.seconds for clip in found)
            total = speech + sum(clip.pause_after for clip in found)
            summary = f"{len(found)} sentences spoken, {total / 60:.1f} minutes with pauses, made in {took / 60:.1f} minutes"
            runlog.finish_step(conn, run.id, STEP, detail=summary)
    except SQLAlchemyError as exc:
        raise VoiceError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    changed = [(line.text, texts[line.id]) for line in lines if texts[line.id] != line.text]
    write_report(root, run_date, STEP, [
        f"# Step 10, Voice: {run_date.isoformat()}",
        "",
        f"{summary}.",
        "",
        "| | |",
        "| --- | --- |",
        f"| Voice model | {settings['engine']}, on this PC, at {settings['speed']:g} times its own pace |",
        f"| Reference voice | `{settings['reference']}` |",
        f"| Speech | {speech / 60:.1f} minutes |",
        f"| Pauses | {(total - speech) / 60:.1f} minutes |",
        f"| Sentences spoken a second time | {len(again)} |",
        f"| Sentences reused from an earlier try | {len(have)} |",
        "",
        f"## Sentences prepared for speaking ({len(changed)})",
        "",
        "Figures and symbols are written the way they are said. The words of the script are not changed.",
        "",
        "| As written | As spoken |",
        "| --- | --- |",
        *(f"| {written.replace('|', '/')} | {said.replace('|', '/')} |" for written, said in changed),
    ])
    return VoiceResult(run.id, run_date, "voiced", len(found), total, report)
