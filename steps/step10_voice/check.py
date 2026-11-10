"""Step 10's check by ear: Whisper writes down each clip, and a clip that does not say its sentence is spoken again.

The voice model sometimes skips words, repeats them, garbles a number or stops before the end of a sentence. The
worker's own checks (length, long pauses, loudness) catch some of this; reading back what was actually said catches
the rest. Whisper writes figures, units and some names its own way ("28th", "64GB", "Allama" for Ollama); both sides are written alike
first, and a clip is fine if it says the sentence as written or as it was given to the voice.
"""

import json
import logging
import os
import re
import subprocess
from decimal import Decimal
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Callable

LISTENER = Path(__file__).with_name("listener.py")
LISTEN_LIMIT = 30 * 60  # seconds Whisper may take for one batch of clips
# clips [{"id", "file"}] -> {id: {"text"} or {"error"}}
Listen = Callable[[list[dict]], dict]

# --- Writing a sentence as plain tokens, the same on both sides --------------------------------------------------
# Whisper writes what it hears its own way: "28th" for 28, "64GB" for 64 gigabytes, "handwritten" for hand-written,
# "flavor" for flavour. The sentence and what was heard go through the same rules, so such a difference is gone
# before the two are compared and only a real difference is left.

ONES = {word: n for n, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen".split())}
TENS = {word: 10 * n for n, word in enumerate("zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()) if n > 1}
SCALE_WORDS = {"thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}
SCALE_LETTERS = {"k": "thousand", "m": "million", "b": "billion", "bn": "billion", "mn": "million", "tn": "trillion"}
CURRENCIES = {"$": "dollar", "£": "pound", "€": "euro"}
MONEY = set(CURRENCIES.values())
# one spelling for the unit and money words, singular
UNITS = {"dollars": "dollar", "pounds": "pound", "euros": "euro", "cents": "cent",
         "gigabytes": "gb", "gigabyte": "gb", "gib": "gb", "gibibytes": "gb", "gibibyte": "gb",
         "megabytes": "mb", "megabyte": "mb", "mib": "mb", "terabytes": "tb", "terabyte": "tb", "tib": "tb",
         "kilobytes": "kb", "kilobyte": "kb", "kib": "kb", "billions": "billion", "millions": "million",
         "trillions": "trillion", "thousands": "thousand"}
# Small words: one dropped, added or swapped is a slip of Whisper's ear, not a fault. Words that change the meaning are
# left out of the list: not, no, never, he/she/we/they, who/what/where, and every figure and name.
SMALL_WORDS = set(
    "a an the and or but of to in on at for by with from as is are was were be been it its this that these those do does "
    "did have has had will would can could should may might shall so if than then there their your also just up out about "
    "into over".split())
CONTRACTED = {"'re": " are", "'ve": " have", "'ll": " will", "'m": " am", "'d": " would", "n't": " not"}
IS_AFTER = {"it", "that", "there", "here", "he", "she", "what", "who", "where", "how", "when", "why"}
SLACK_EVERY = 12  # one small-word slip is let pass in a sentence, and one more for every 12 words


def _figure(number: str) -> str:
    """A figure without its trailing zeros: 5.00 -> 5, 12.50 -> 12.5."""
    return number.rstrip("0").rstrip(".") if "." in number else number


def _scaled(number: str, scale: str) -> str:
    """9.65 billion -> 9650000000, so that "256 thousand", "256K" and "256,000" are one figure."""
    return format((Decimal(number) * SCALE_WORDS[scale]).normalize(), "f")


def _money(m: re.Match) -> str:
    """$30.50 -> 30 dollar 50 cent, $0.07 -> 7 cent, $95bn -> 95 billion dollar, £100m -> 100 million pound."""
    cur, number = CURRENCIES[m.group(1)], m.group(2)
    scale = SCALE_LETTERS.get(m.group(3) or "", m.group(3))
    if scale:
        return f" {_scaled(number, scale)} {cur} "
    whole, _, cents = number.partition(".")
    if len(cents) == 2 and int(cents):
        return f" {int(cents)} cent " if int(whole) == 0 else f" {int(whole)} {cur} {int(cents)} cent "
    return f" {_figure(number)} {cur} "


def _figures_in_words(tokens: list[str]) -> list[str]:
    """twenty -> 20, forty three thousand three hundred eighty four -> 43384: figures written in words, as figures."""
    result, i = [], 0
    while i < len(tokens):
        if tokens[i] not in ONES and tokens[i] not in TENS and tokens[i] != "hundred":
            result.append(tokens[i])
            i += 1
            continue
        total = current = 0
        last = "start"
        while i < len(tokens):
            word = tokens[i]
            if word in ONES and (last in ("start", "hundred") or last == "tens" and 0 < ONES[word] < 10):
                current += ONES[word]
                last = "ones"
            elif word in TENS and last in ("start", "hundred"):
                current += TENS[word]
                last = "tens"
            elif word == "hundred" and last in ("start", "ones", "tens"):
                current = (current or 1) * 100
                last = "hundred"
            elif word == "thousand" and last != "start" and total == 0:
                total, current, last = current * 1000, 0, "start"
            else:
                break
            i += 1
        result.append(str(total + current))
    return result


def words(text: str) -> list[str]:
    """A sentence as plain tokens to compare: figures, units, money, ordinals and contractions written one way."""
    text = text.lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    text = re.sub(r"[‐‑–—]", "-", text)
    text = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", text)  # 2,399 -> 2399
    text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", text)  # 28th -> 28
    text = re.sub(r"\bper cent\b", " percent ", text).replace("%", " percent ")
    text = text.replace("&", " and ")
    text = re.sub(r"([$£€])\s*(\d+(?:\.\d+)?)\s*(thousand|million|billion|trillion|bn|mn|tn|[kmb])?(?![a-z])", _money, text)
    text = re.sub(r"(?<=\d)(bn|mn|tn|[kmb])\b", lambda m: " " + SCALE_LETTERS[m.group(1)] + " ", text)  # 164M, 284B, 256K
    text = re.sub(r"(?<=\d)x\b", " times ", text)  # 2.2x
    text = re.sub(r"\bv(?=\d)", "version ", text)  # v1.1
    text = re.sub(r"\b([a-z])\.(?=[a-z]\b)", r"\1", text)  # U.S. -> us
    text = re.sub(r"\bcannot\b", "can not", text).replace("let's", "let us")
    text = re.sub(r"\b(\w+)'s\b", lambda m: m.group(1) + (" is" if m.group(1) in IS_AFTER else ""), text)  # a possessive goes
    for short, long in CONTRACTED.items():
        text = text.replace(short, long)
    text = text.replace("'", "")
    text = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", text)  # 64gb -> 64 gb, qwen3 -> qwen 3
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # a full stop goes, a decimal point stays
    text = re.sub(r"[^a-z0-9. ]", " ", text)
    result = []
    for token in _figures_in_words(text.split()):
        if re.fullmatch(r"\d+\.\d+", token):
            token = _figure(token)
        token = UNITS.get(token, token)
        if token in SCALE_WORDS and result and re.fullmatch(r"\d+(?:\.\d+)?", result[-1]):
            result[-1] = _scaled(result[-1], token)
        elif token == "and" and len(result) >= 2 and result[-1] in MONEY:
            continue  # 2,599 dollars and 99 cents
        else:
            result.append(token)
    return result


# --- Telling two words apart --------------------------------------------------------------------------------------

# British and American spellings, both brought to the American one. Only endings that follow a pattern, and none that
# could turn one real word into another: "four", "hour" and "your" (one letter before "our") are left alone.
AMERICAN = [
    (r"(?<=[a-z]{2})our(?=(?:s|ed|ing|ite|able|ful|less|er|ers)?$)", "or"),  # colour, flavour, behaviour
    (r"is(?=(?:ation|ations|e|es|ed|ing|er|ers|able)$)", "iz"),  # organise, characterisation
    (r"ys(?=(?:e|es|ed|ing|ation)$)", "yz"),  # analyse
    (r"(?<=[a-z]{2})tre(?=s?$)", "ter"),  # centre, theatre
    (r"(?<=[a-z]{3})ogue(?=s?$)", "og"),  # catalogue
    (r"(?<=[a-z]{2})ence(?=s?$)", "ense"),  # defence, licence
    (r"(?<=el)l(?=(?:ed|ing|er|ers)$)", ""),  # labelled, travelling
    (r"dgement", "dgment"),  # judgement
    (r"^scept", "skept"),  # sceptic
    (r"mme(?=s?$)", "m"),  # programme
]


def _american(word: str) -> str:
    for pattern, repl in AMERICAN:
        word = re.sub(pattern, repl, word)
    return word


def _skeleton(word: str) -> str:
    return re.sub(r"[aeiouyw]", "", word)


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


_PHONEMES = []


@lru_cache(maxsize=None)
def _sound(word: str) -> str | None:
    """How espeak-ng says a word, or None when it is not available (then only the spelling rules are used)."""
    try:
        if not _PHONEMES:
            import espeakng_loader
            from phonemizer.backend import EspeakBackend
            from phonemizer.backend.espeak.wrapper import EspeakWrapper
            EspeakWrapper.set_library(espeakng_loader.get_library_path())
            EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
            _PHONEMES.append(EspeakBackend("en-us", with_stress=False, logger=logging.getLogger("check-phonemes")))
        return _PHONEMES[0].phonemize([word], strip=True)[0] or None
    except Exception:
        return None


def _alike(a: str, b: str, name: bool = False) -> bool:
    """Two words that are the same word as Whisper may write it: color and colour, test and tests, weight and wait (said
    alike). A name may also be spelt its own way (Ollama, Allama; Claude, Clawed): the letters must agree 3/4 and so must
    the consonants 9/10, so Karpathy is not Kaipathy (the r is a consonant), Huang is not Wang or Hong, and Claude is not
    Clog. An ordinary word is not let off like that: boot is not boat. Figures and short words must be equal."""
    if a == b:
        return True
    if re.search(r"\d", a + b) or min(len(a), len(b)) < 3 or max(len(a), len(b)) < 4:
        return False
    a, b = _american(a), _american(b)
    if a == b:
        return True
    short, long = sorted((a, b), key=len)
    if long.startswith(short) and long[len(short):] in ("s", "es", "ed", "d", "ing", "er"):
        return True  # tests / test, confirmed / confirm
    if _sound(a) is not None and _sound(a) == _sound(b):
        return True  # said alike, spelt differently: weight and wait, tonnes and tons
    return name and len(_skeleton(a)) >= 2 and _ratio(a, b) >= 0.75 and _ratio(_skeleton(a), _skeleton(b)) >= 0.9


def _same(a: list[str], b: list[str], names: frozenset[str]) -> bool:
    """Two runs of tokens that are the same: spaced or joined ("hand written", "handwritten", "10 17", "1017"), word for
    word, or one name written two ways. A figure must be equal to the other."""
    if not a and not b:
        return True
    if not a or not b:
        return False
    if "".join(a) == "".join(b) or _american("".join(a)) == _american("".join(b)):
        return True
    if len(a) == len(b) and all(_alike(x, y, x in names) for x, y in zip(a, b)):
        return True
    return not re.search(r"\d", "".join(a + b)) and _alike("".join(a), "".join(b), all(x in names for x in a))


def _find(said: list[str], got: list[str], names: frozenset[str]) -> list[str]:
    """The problems found in comparing the tokens of the sentence with those that were heard."""
    problems, small, added = [], [], []

    def put(a: list[str], b: list[str]) -> str:
        if not b:
            return f"\"{' '.join(a)}\" was not heard"
        if not a:
            return f"\"{' '.join(b)}\" was heard but is not in the sentence"
        return f"\"{' '.join(a)}\" was heard as \"{' '.join(b)}\""

    for op, i1, i2, j1, j2 in SequenceMatcher(None, said, got, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        a, b = said[i1:i2], got[j1:j2]
        if not a and (got[j1 - len(b):j1] == b or got[j2:j2 + len(b)] == b):
            problems.append(f"\"{' '.join(b)}\" was said twice")
            added += b
            continue
        if _same(a, b, names):
            continue
        ca, cb = [w for w in a if w not in SMALL_WORDS], [w for w in b if w not in SMALL_WORDS]
        if _same(ca, cb, names):
            small += [put(a, b)] * max(len(a) - len(ca), len(b) - len(cb))
            continue
        problems.append(put(a, b))
        if not a:
            added += b
    if len(added) >= 3:
        problems.append(f"extra words heard: \"{' '.join(added)}\"")
    if len(small) > 1 + len(said) // SLACK_EVERY:
        problems += small
    return problems


def _names(text: str) -> frozenset[str]:
    """The names in a sentence: its capitalised words, as tokens. Only a name may be written by Whisper in its own way."""
    return frozenset(token for word in re.findall(r"[A-Za-z][\w'’]*", text) if word[0].isupper() for token in words(word))


def _verdict(sentence: str, heard: str) -> list[str]:
    said, got = words(sentence), words(heard)
    if not said:
        return []
    if not got:
        return ["nothing was heard"]
    return _find(said, got, _names(sentence))


def fault(sentence: str, heard: str, spoken: str | None = None) -> str | None:
    """What is wrong with a clip, from what Whisper heard in it, or None if it says its sentence.

    `sentence` is the sentence as the script writes it and `spoken` the text the voice was given for it, with its
    respellings ("I-dea" for AIdea, "Clawd" for Claude). A clip is fine if it says either one.
    """
    found = _verdict(sentence, heard)
    if found and spoken and spoken != sentence:
        again = _verdict(spoken, heard)
        found = again if len(again) < len(found) else found
    return "; ".join(dict.fromkeys(found)) or None


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
    problems = {key: (fault(item["plain"], heard[key]["text"], item.get("text")) if "text" in heard.get(key, {}) else None) for key, item in by_id.items()}
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
            problem = fault(item["plain"], again[key]["text"], item.get("text")) if "file" in take and "text" in again.get(key, {}) else "the retake failed"
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
