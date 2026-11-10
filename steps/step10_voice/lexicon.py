"""The pronunciation lexicon: how to spell a name so that the voice says it right, with the test behind each entry.

`voice/lexicon.toml` holds one table per word as the script writes it:

    ["Huang"]
    say = "Hwahng"            # what the voice is given instead
    passes = 5                # takes out of `of` that Whisper heard as the name
    of = 5
    tested = "2026-11-10"
    sentence = "..."          # one of the real sentences it was tested in

A word the search could not make reliable has `status = "none"` instead of `say`: it is spoken as written, and
the best spelling found and its score are kept so it is not searched again for nothing. `voice/common-words.txt`
(the 15,000 commonest English words, from Peter Norvig's count_1w list of Google's n-gram counts) tells a name from
an ordinary word, so that step 10 can list the names in a script that have not been tested yet.
"""

import re
import tomllib
from collections import Counter
from pathlib import Path

LEXICON = Path("voice") / "lexicon.toml"
COMMON = Path("voice") / "common-words.txt"
PLACE = 0xE000  # a respelling is held in the text as one private-use character, which no other rule touches
MINIMUM = 4  # takes out of 5 that must be right for a spelling to be used


def load(root: Path) -> dict[str, dict]:
    """Every entry of the lexicon, by the word as written. Missing or unreadable file: no entries."""
    try:
        return {word: dict(entry) for word, entry in tomllib.loads((root / LEXICON).read_text(encoding="utf-8")).items()
                if isinstance(entry, dict)}
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def says(entries: dict[str, dict]) -> dict[str, str]:
    """The respellings to use: only tested entries with a spelling and a good enough score."""
    return {word: entry["say"] for word, entry in entries.items()
            if entry.get("say") and entry.get("status") != "none" and entry.get("passes", 0) >= MINIMUM}


def save(root: Path, entries: dict[str, dict]) -> None:
    def value(item) -> str:
        return '"' + item.replace("\\", "\\\\").replace('"', '\\"') + '"' if isinstance(item, str) else str(item)

    lines = ["# The pronunciation lexicon: see steps/step10_voice/lexicon.py. Entries are written by",
             "# experiments/voice_bench/lexicon.py after each spelling was voiced 5 times in real sentences.", ""]
    for word in sorted(entries, key=str.lower):
        lines.append(f"[{value(word)}]")
        lines += [f"{key} = {value(item)}" for key, item in entries[word].items()]
        lines.append("")
    (root / LEXICON).write_text("\n".join(lines), encoding="utf-8")


def apply(text: str, say: dict[str, str]) -> tuple[str, list[str]]:
    """The text with each word replaced by its spelling, longest word first and in one pass, so that one respelling
    is never respelt by another. Returns the text with a placeholder for each respelling, and the respellings (up to 4,000 of them in one text)."""
    if not say:
        return text, []
    ordered = sorted(say, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w$-])(?:" + "|".join(re.escape(word) for word in ordered) + r")(?![\w-])")
    found: list[str] = []

    def put(match: re.Match) -> str:
        found.append(say[match.group()])
        return chr(PLACE + len(found) - 1)

    return pattern.sub(put, text), found


def restore(text: str, found: list[str]) -> str:
    return re.sub(f"[{chr(PLACE)}-{chr(PLACE + 0xFFF)}]", lambda m: found[ord(m.group()) - PLACE], text)


def common_words(root: Path) -> frozenset[str]:
    try:
        return frozenset((root / COMMON).read_text(encoding="utf-8").split())
    except OSError:
        return frozenset()


def untested(texts: list[str], entries: dict[str, dict], say: dict[str, str] | None, root: Path) -> list[tuple[str, int]]:
    """Names in the script that the lexicon has not tested: capitalised or camel-case words, not common English words,
    not part of a word in the lexicon or in [voice.say]. Returns (name, how often), the most often first."""
    common = common_words(root)
    if not common:
        return []
    known = {part.lower() for word in [*entries, *(say or {})] for part in re.findall(r"[A-Za-z]+", word)}
    counts: Counter = Counter()
    for text in texts:
        for match in re.finditer(r"(?<![\w'’])([A-Z][A-Za-z]{2,}|[a-z]+[A-Z][A-Za-z]*)(?![\w])", text):
            word = match.group(1)
            if word.isupper() or word.lower() in common or word.lower() in known:
                continue  # all capitals are read out as letters, and are another matter
            counts[word] += 1
    return counts.most_common()
