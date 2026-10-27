"""Step 10's check by ear: Whisper writes down each clip, and a clip that does not say its sentence is spoken again.

The voice model sometimes skips words, repeats them, garbles a number or stops before the end of a sentence. The
worker's own checks (length, long pauses, loudness) catch some of this; reading back what was actually said catches
the rest. Whisper writes some names its own way ("Allama" for Ollama), so a difference of a word or two is let pass.
"""

import json
import os
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

LISTENER = Path(__file__).with_name("listener.py")
LISTEN_LIMIT = 30 * 60  # seconds Whisper may take for one batch of clips
RUN = 3  # this many words in a row missing, added or changed is a fault; fewer is a name Whisper spells its own way
LOWEST_MATCH = 0.8  # share of the sentence's words that must be heard
# clips [{"id", "file"}] -> {id: {"text"} or {"error"}}
Listen = Callable[[list[dict]], dict]

SMALL = {word: str(n) for n, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty".split())}


def words(text: str) -> list[str]:
    """A sentence as words to compare: lower case, no punctuation, figures written alike on both sides."""
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)  # 2,399 -> 2399
    text = text.replace("%", " percent ").replace("&", " and ").replace("$", " ")
    text = re.sub(r"[-–—/|_]", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # a full stop goes, a decimal point stays
    text = re.sub(r"[^a-z0-9.' ]", " ", text).replace("'", "")
    return [SMALL.get(word, word) for word in text.split()]


def _alike(a: list[str], b: list[str]) -> bool:
    """Two runs of words that differ only in spelling or spacing: "open ai" and "openai", "allama" and "ollama"."""
    return SequenceMatcher(None, "".join(a), "".join(b), autojunk=False).ratio() >= 0.75


def _numbers(said: list[str], heard: list[str]) -> list[str]:
    """Figures of the sentence that were not heard. Two figures heard side by side may be one said in pairs: 10 17."""
    found = set(heard) | {a + b for a, b in zip(heard, heard[1:]) if a.isdigit() and b.isdigit()}
    found |= {word.rstrip("0").rstrip(".") for word in heard if "." in word}
    return [word for word in said if re.fullmatch(r"\d+(?:\.\d+)?", word) and (len(word) > 1 or "." in word)
            and word not in found and word.rstrip("0").rstrip(".") not in found]


def fault(sentence: str, heard: str) -> str | None:
    """What is wrong with a clip, from what Whisper heard in it, or None if it says its sentence."""
    said, got = words(sentence), words(heard)
    if not said:
        return None
    if not got:
        return "nothing was heard"
    blocks = SequenceMatcher(None, said, got, autojunk=False)
    problems, extra = [], []
    for op, i1, i2, j1, j2 in blocks.get_opcodes():
        if op == "equal" or _alike(said[i1:i2], got[j1:j2]):
            continue
        if i2 - i1 >= RUN:
            problems.append(f"\"{' '.join(said[i1:i2])}\" was not heard" + (f" (heard \"{' '.join(got[j1:j2])}\")" if j2 > j1 else ""))
        elif j2 - j1 >= RUN:
            problems.append(f"\"{' '.join(got[j1:j2])}\" was heard but is not in the sentence")
        elif j2 - j1 > i2 - i1:
            added = got[j1:j2][i2 - i1:]
            if len(added) >= 2 and got[j1 - len(added):j1] == added:
                problems.append(f"\"{' '.join(added)}\" was said twice")
            extra += added
    # Words said twice here and there, as when the voice stutters or goes back over a phrase.
    if len(extra) >= RUN:
        problems.append(f"extra words heard: \"{' '.join(extra)}\"")
    matched = sum(size for _, _, size in blocks.get_matching_blocks())
    last = max((i + size for i, _, size in blocks.get_matching_blocks() if size), default=0)
    if len(said) >= 4 and last <= len(said) - 2 and not _alike(said[-2:], got[-2:]):
        problems.append(f"the ending \"{' '.join(said[-2:])}\" was not heard")
    missing = _numbers(said, got)
    if missing:
        problems.append(f"the figure{'s' if len(missing) > 1 else ''} {', '.join(missing)} not heard")
    if not problems and len(said) >= 4 and matched / len(said) < LOWEST_MATCH:
        problems.append(f"only {matched} of {len(said)} words heard as written")
    return "; ".join(dict.fromkeys(problems)) or None


def badness(problem: str | None) -> int:
    """How bad a take is, to pick the better of two: the number of things wrong with it."""
    return 0 if problem is None else problem.count(";") + 1


def run_listener(root: Path, voice: dict, folder: Path) -> Listen:
    """Hears clips with Whisper, in the voice model's Python environment."""

    def listen(found: list[dict]) -> dict:
        python = root / voice["python"]
        folder.mkdir(parents=True, exist_ok=True)
        job = folder / "listen.json"
        job.write_text(json.dumps({"clips": found, "model": voice.get("listen_model", "medium.en")}), encoding="utf-8")
        env = dict(os.environ, HF_HOME=str(root / "data" / "models" / "huggingface"))
        answer = job.with_name("heard.json")
        answer.unlink(missing_ok=True)
        try:
            subprocess.run([str(python), str(LISTENER), str(job)], env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=LISTEN_LIMIT)
        except subprocess.TimeoutExpired:
            pass
        heard = json.loads(answer.read_text(encoding="utf-8"))["heard"] if answer.exists() else {}
        job.unlink(missing_ok=True)
        answer.unlink(missing_ok=True)
        return {int(key): value for key, value in heard.items()}

    return listen


def recheck(items: list[dict], made: dict, speak, listen: Listen, voice: dict, folder: Path, rounds: int = 2,
            retake: Callable[[dict], dict] = lambda item: item) -> list[dict]:
    """Hear every clip in `made`, speak again the ones that do not say their sentence, and keep the better take.

    `items` are what was given to the voice: "id", "text" and "plain", the sentence as the script writes it, which
    is what the clip is compared with. `made` is updated in place. Returns one entry per clip that was found
    wrong: its sentence, what was wrong at first, and what is still wrong (None when a retake fixed it).

    Nothing here stops the run: a clip that is still wrong after the last round is kept in its best take and
    listed for a person to hear.
    """
    by_id = {item["id"]: item for item in items if "file" in (made.get(item["id"]) or {})}
    if not by_id:
        return []
    heard = listen([{"id": key, "file": made[key]["file"]} for key in by_id])
    problems = {key: (fault(item["plain"], heard[key]["text"]) if "text" in heard.get(key, {}) else None) for key, item in by_id.items()}
    first = {key: problem for key, problem in problems.items() if problem}
    for _ in range(rounds):
        wrong = [by_id[key] for key, problem in problems.items() if problem]
        if not wrong:
            break
        # The take in hand is put aside, so that the new one can be compared with it.
        kept = {}
        for item in wrong:
            old = Path(made[item["id"]]["file"])
            aside = old.with_name(f"{old.stem}-kept{old.suffix}")
            os.replace(old, aside)
            kept[item["id"]] = (dict(made[item["id"]], file=str(aside)), old)
        new = speak([retake(item) for item in wrong], voice, folder)
        spoken = [item for item in wrong if "file" in (new.get(item["id"]) or {})]
        again = listen([{"id": item["id"], "file": new[item["id"]]["file"]} for item in spoken]) if spoken else {}
        for item in wrong:
            key = item["id"]
            aside, old = kept[key]
            take = new.get(key) or {}
            problem = fault(item["plain"], again[key]["text"]) if "file" in take and "text" in again.get(key, {}) else "the retake failed"
            if "file" in take and badness(problem) < badness(problems[key]):
                Path(aside["file"]).unlink(missing_ok=True)
                made[key] = {"file": take["file"], "seconds": take["seconds"]}
                problems[key] = problem
            else:
                if "file" in take and Path(take["file"]) != old:
                    Path(take["file"]).unlink(missing_ok=True)
                os.replace(aside["file"], old)
                made[key] = dict(aside, file=str(old))
    return [{"id": key, "text": by_id[key]["plain"], "was": problem, "left": problems[key]} for key, problem in first.items()]
