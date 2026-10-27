"""Step 10, Voice: turn the final script into speech, one clip per sentence."""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError

from common import clips, db, episodes, formats, runlog, script
from common.report import step_folder, write_report
from common.settings import ROOT, database_url, load
from common.text import word_count
from steps.step10_voice.check import Listen, recheck, run_listener

STEP = 10
WORKER = Path(__file__).with_name("worker.py")
WORKER_LIMIT = 90 * 60  # seconds the voice model may take for one episode
# A clip far too short or far too long for its words means the model slipped: it is spoken again.
SLOWEST, FASTEST = 0.8, 7.0  # words a second
RETRY_PHRASE = 12  # on the second try, a sentence longer than this many words is spoken in phrases
# sentences to speak, the voice settings, the folder for the clips -> {sentence id: {"file", "seconds"} or {"error"}}
Speak = Callable[[list[dict], dict, Path], dict]

SCALES = {"k": "thousand", "m": "million", "b": "billion", "t": "trillion", "bn": "billion"}
SIZES = {"K": "kilobytes", "M": "megabytes", "G": "gigabytes", "T": "terabytes"}
MONTHS = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April", "Jun": "June", "Jul": "July",
          "Aug": "August", "Sept": "September", "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December"}
PER = {"s": "second", "sec": "second", "min": "minute", "h": "hour", "hr": "hour", "day": "day", "wk": "week",
       "week": "week", "mo": "month", "month": "month", "yr": "year", "year": "year"}
# A whole number as written: 1,600 or 1600, but not the comma after "$30," that only ends a phrase.
WHOLE = r"\d{1,3}(?:,\d{3})+|\d+"
AMOUNT = rf"(?:{WHOLE})(?:\.\d+)?"
# Words after "the $2,399" that show the amount is not standing before a noun, so it stays "dollars".
NOT_NOUNS = {"a", "an", "and", "apiece", "are", "as", "at", "but", "by", "can", "could", "each", "for", "from", "had",
             "has", "in", "into", "is", "it", "of", "on", "or", "over", "per", "that", "the", "to", "was", "were",
             "which", "will", "with", "would"}


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
    # A hyphen of another kind is said as the plain one: "low‑resource", with a no-break hyphen, came out
    # "low-free source" on 2026-10-20.
    text = re.sub(r"[‐‑]", "-", text)
    text = re.sub(r"(?<=\d)\s?×", "x", text)  # 21.5× is 21.5x: "5–6.5×" came out "5 6.5 times" on 2026-10-21
    for written, said in (say or {}).items():
        text = re.sub(rf"(?<![\w$-]){re.escape(written)}(?![\w-])", said, text)
    # A name strung together with hyphens is said in parts: Deepseek-V4.1-Flash-1017 came out "version 4.1.1".
    text = re.sub(r"\b[\w.]+(?:-[\w.]+){2,}", lambda m: m.group().replace("-", " ") if re.search(r"\d", m.group()) else m.group(), text)
    # $8-9 million -> 8 to 9 million dollars, not "8 dollars-9 million"
    text = re.sub(
        rf"\$({AMOUNT})\s*[-–]\s*\$?({AMOUNT})(?:\s*(thousand|million|billion|trillion)\b|(bn|[KkMmBbTt])\b)?",
        lambda m: f"{m.group(1)} to {m.group(2)} {m.group(3) or SCALES.get((m.group(4) or '').lower(), '')} dollars".replace("  ", " "),
        text,
    )
    # $300 million, $4B, $20 -> 300 million dollars, 4 billion dollars, 20 dollars
    # Before a noun it is "dollar": "a 1.8 billion dollar push", "the 85 to 95,000 dollar range". That is the case
    # after a, the, its, a possessive or a range's "to", when a noun follows: "The $2,399 is" stays "dollars".
    # A price in cents is said with them: $2,599.99 -> 2,599 dollars and 99 cents; $504.00 -> 504 dollars; $0.20 -> 20 cents.
    # One dollar is "dollar": $1 / $6 came out "1 dollars" on 2026-10-26.
    def dollars(m: re.Match) -> str:
        whole, cents, scale = m.group(2), m.group(3), m.group(4) or SCALES.get((m.group(5) or "").lower(), "")
        after = re.match(r"\s+([a-z][a-z-]*)\b", m.string[m.end():])
        before_noun = m.group(1) and after and after.group(1) not in NOT_NOUNS
        one = whole == "1" and not scale and (not cents or len(cents) == 2)
        unit = "dollar" if before_noun or one else "dollars"
        if scale:
            return (m.group(1) or "") + f"{whole}{'.' + cents if cents else ''} {scale} {unit}"
        if whole == "0" and cents and len(cents) > 2 and int(cents):
            # $0.0035 -> 0.35 cents: "0.0035 dollars" was heard "0.35 dollars" on 2026-10-21
            amount = format((Decimal("0." + cents) * 100).normalize(), "f")
            return (m.group(1) or "") + f"{amount} {'cent' if before_noun else 'cents'}"
        if cents and len(cents) == 2:
            if whole == "0" and int(cents):
                return (m.group(1) or "") + f"{int(cents)} {'cent' if before_noun or cents == '01' else 'cents'}"
            return (m.group(1) or "") + f"{whole} {unit}" + (f" and {int(cents)} cents" if int(cents) else "")
        return (m.group(1) or "") + f"{whole}{'.' + cents if cents else ''} {unit}"

    text = re.sub(
        rf"(\b(?i:an?|the|its|his|her|their|our)\s+|['’]s\s+|\d\s+to\s+)?\$({WHOLE})(?:\.(\d+))?"
        r"(?:\s*(thousand|million|billion|trillion)\b|(bn|[KkMmBbTt])\b)?(?:\s+USD\b)?",
        dollars,
        text,
    )
    # Prices set side by side with spaced slashes are a list: "$5 / $30 / $0.50" lost its figures on 2026-10-26.
    text = re.sub(r"\s+/\s+", ", ", text)
    # r/TrueOpenSource -> r slash TrueOpenSource: heard "arsh lakshu opensource" on 2026-10-26
    text = re.sub(r"\br/(?=\w)", "r slash ", text)
    # Qwen3.5-9B -> Qwen 3.5, 9 billion: a name's version is said apart from it, and from the size after it.
    # "Qwen3.5" came out "Quent 3.3.5" and "Qwen3.5-9B" "Qwen 3.59 billion" on 2026-10-26.
    text = re.sub(r"\b([A-Z][a-z]+)(\d+(?:\.\d+)*)(?:(-)(?=\d+(?:\.\d+)?[KMBT]\b)|(?![\w.-]))",
                  lambda m: f"{m.group(1)} {m.group(2)}" + (", " if m.group(3) else ""), text)
    # 501B, 270M, 1T, 8K -> 501 billion, 270 million, 1 trillion, 8 thousand
    text = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)([KMBT])\b", lambda m: f"{m.group(1)} {SCALES[m.group(2).lower()]}", text)
    # 191MB, 8GB, 270 GiB -> 191 megabytes, 8 gigabytes, 270 gigabytes ("Gi B" on 2026-10-21)
    text = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s?([KMGT])i?B\b", lambda m: f"{m.group(1)} {SIZES[m.group(2)]}", text)
    # A scale word joined to what follows by a hyphen is said as two words: "501 billion-parameter" stays, but
    # "501 billion-A23B" would be read as one tangle.
    text = re.sub(r"\b(thousand|million|billion|trillion)-(?=[A-Z0-9])", r"\1 ", text)
    text = re.sub(r"(\d)\s?%", r"\1 percent", text)
    # 4–8x -> 4 to 8 times: said "4x 8x" on 2026-10-20
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s?[–-]\s?(\d+(?:\.\d+)?)x\b", r"\1 to \2 times", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)x\b", r"\1 times", text)
    # 10 ms -> 10 milliseconds: said "10 mesemes" twice on 2026-10-20
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s?ms\b", lambda m: f"{m.group(1)} millisecond{'' if m.group(1) == '1' else 's'}", text)
    # Oct. 20, 2026 -> October 20, 2026: said "AUC 202026" on 2026-10-20
    text = re.sub(rf"\b({'|'.join(MONTHS)})\.?(?=\s+\d)", lambda m: MONTHS[m.group(1)], text)
    # tokens/s, $0.0035/min -> tokens per second, per minute: said "token slash S" on 2026-10-21
    text = re.sub(rf"(?<=\w)/({'|'.join(PER)})\b", lambda m: f" per {PER[m.group(1)]}", text)
    # Code as it is written, said the way a programmer reads it aloud: device_map -> device map, pipe.to -> pipe dot
    # to. On 2026-10-21 these came out "device cotton map", "pipe ducette" and "torch XLAR".
    text = re.sub(r"\b(e\.g\.|i\.e\.)", lambda m: "for example" if m.group(1) == "e.g." else "that is", text)
    text = re.sub(r"(?<=[A-Za-z0-9])_(?=[A-Za-z0-9])", " ", text)
    text = re.sub(r"(?<=[A-Za-z])\.(?=[a-z])", " dot ", text)
    text = re.sub(r"\bdot ai\b", "dot A I", text)  # Otter.ai
    # V4.1, v1.1, DSv4 -> version 4.1, version 1.1, DS version 4
    text = re.sub(r"(?<![A-Za-z])[vV](\d+(?:\.\d+)*)\b", r"version \1", text)
    text = re.sub(r"(?<=[A-Z])v(\d+(?:\.\d+)*)\b", r" version \1", text)
    # A four-figure number without a comma that is not a year is a code: model 1017, port 8081, RTX 4060. The voice
    # garbled "Flash 1017" three different ways; in pairs it is said the way people say it, "ten seventeen".
    text = re.sub(
        r"(?<![\d.,/:$])\b([1-9]\d)(\d\d)\b(?![.,]\d)(?!\s+(?:dollars?|percent|times)\b)",
        lambda m: m.group() if m.group(1) in ("19", "20") or m.group(2) == "00"
        else f"{m.group(1)} {'oh ' + m.group(2)[1] if m.group(2)[0] == '0' else m.group(2)}",
        text,
    )
    # A number with a comma is said in words: the voice read "2,399" as "2,039" four times out of four on 2026-10-18.
    text = re.sub(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?![\d,]|\.\d)", lambda m: in_words(int(m.group().replace(",", ""))), text)
    # A headline's "|" between its parts is a pause.
    text = re.sub(r"\s+\|\s+", ", ", text)
    text = text.replace(" & ", " and ").replace("~", "about ")
    text = re.sub(r"[\[\]]", "", text)
    text = re.sub(r"[A-Za-z]+", lambda m: spaced(m.group()), text)
    return re.sub(r"\s+", " ", text).strip()


ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def in_words(n: int) -> str:
    """2399 -> two thousand three hundred ninety-nine."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " hundred" + (" " + in_words(n % 100) if n % 100 else "")
    for size, name in ((10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand")):
        if n >= size:
            return in_words(n // size) + " " + name + (" " + in_words(n % size) if n % size else "")
    raise ValueError(n)


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
                # Settings added on 2026-10-21; a run started before then has none and is spoken as it was.
                **{key: voice.get(key, default) for key, default in (("clean", False), ("retakes", 0), ("longest_pause", 2.0))},
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


def heard_summary(checks: list[dict]) -> str:
    """Step 10's summary of the check by ear: how many clips were wrong, and how many still are."""
    left = sum(1 for check in checks if check["left"])
    return f"{len(checks)} found wrong by ear, {len(checks) - left} fixed" + (f", {left} to hear" if left else "")


def heard_report(what: str, checks: list[dict], listen) -> list[str]:
    """The report's section on the check by ear: every clip found wrong, and what became of it."""
    if not listen:
        return []
    lines = ["", f"## Checked by ear: {what}", "",
             f"Whisper wrote down every clip and compared it with its sentence: {heard_summary(checks)}."]
    left = [check for check in checks if check["left"]]
    if left:
        lines += ["", "Still wrong after the retakes. Listen to these before publishing:", "",
                  *(f"- \"{check['text']}\": {check['left']}" for check in left)]
    fixed = [check for check in checks if not check["left"]]
    if fixed:
        lines += ["", "Fixed by a retake:", "", *(f"- \"{check['text']}\": {check['was']}" for check in fixed)]
    return lines


def _formats_lines(conn, run) -> list[str]:
    """What became of each longer episode in this step, for the report."""
    lines = []
    for name, row in formats.scripts_of(conn, run.id).items():
        if name not in formats.wanted(run.settings):
            continue
        about, voices = formats.FORMATS[name], run.settings["formats"]["voices"]
        lines += ["", f"## The {about['name']} ({about['label']})", ""]
        if row.note:
            lines.append(row.note[0].upper() + row.note[1:] + ".")
        elif row.clips:
            lines.append(f"{len(row.clips)} pieces spoken in {(row.voice_seconds or 0) / 60:.1f} minutes. Step 11 joins them.")
            lines += ["", *(f"- {speaker}: `{voices[formats.VOICES[speaker]]}`" for speaker in about["speakers"])]
        else:
            lines.append("Nothing to speak.")
    return lines


def voice(run_date: date, *, root: Path = ROOT, speak: Speak | None = None, listen: Listen | None = None) -> VoiceResult:
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

        # Each clip is heard back with Whisper and spoken again if it does not say its sentence. Tests that stand in
        # for the voice pass their own `listen`, or none. Settings added on 2026-10-23; an earlier run uses the file's.
        heard_by = {key: settings.get(key, load(root)["voice"].get(key)) for key in ("listen", "listen_model", "listen_rounds")}
        if listen is None and speak is None and heard_by["listen"]:
            listen = run_listener(root, {**settings, **heard_by}, folder)
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
        # The second try speaks a long sentence phrase by phrase: on 2026-10-22 one stopped partway every time whole.
        again = [dict(item, phrases=phrases(item["text"], RETRY_PHRASE)) for item in again]
        if again:
            made.update(speak(again, settings, folder))
        failed = [(item, problem_with(made.get(item["id"]), item["text"])) for item in again]
        failed = [(item, problem) for item, problem in failed if problem]
        checks = []
        if listen and not failed:
            plain = {line.id: line.text for line in lines}
            checks = recheck([dict(item, plain=plain[item["id"]]) for item in wanted], made, speak, listen, settings, folder,
                             rounds=heard_by["listen_rounds"] or 2)
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

        # The longer episodes are spoken after the regular one. Imported here because that module uses this one's helpers.
        from steps.formats.voice import voice_formats
        longer, longer_checks = voice_formats(engine, root, run, settings, speak, folder.parent, listen, heard_by["listen_rounds"] or 2)

        with engine.begin() as conn:
            found = clips.of_run(conn, run.id)
            speech = sum(clip.seconds for clip in found)
            total = speech + sum(clip.pause_after for clip in found)
            summary = f"{len(found)} sentences spoken, {total / 60:.1f} minutes with pauses, made in {took / 60:.1f} minutes"
            if listen:
                summary += f", {heard_summary(checks)}"
            summary += "".join(f"; {one}" for one in longer)
            longer_report = _formats_lines(conn, run)
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
        *heard_report("the episode", checks, listen),
        *longer_report,
        *(line for name, found in longer_checks.items() for line in heard_report(f"the {formats.FORMATS[name]['name']}", found, listen)),
    ])
    return VoiceResult(run.id, run_date, "voiced", len(found), total, report)
