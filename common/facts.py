"""Checking a sentence against source text: every number and every name in it must appear in the source.

This catches wrong facts. It cannot catch a wrong meaning built from the right words.
"""

import math
import re
from dataclasses import dataclass

SCALES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "t": 1e12, "trillion": 1e12}
# 1,674 or 5.4 or 900M or 4 billion or 6th. Not the 23 in A23B, and not the 4 in 5.4.
DIGITS = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?"
    r"(?:(bn|k|m|b|t)(?![a-z])|\s*-?\s*(thousand|million|billion|trillion)\b|(?:st|nd|rd|th)\b)?",
    re.IGNORECASE,
)
SMALL = {
    word: value
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen".split()
    )
} | {word: 10 * tens for tens, word in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)}
LARGE = {"hundred": 100, "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
SPELLED = re.compile(
    rf"\b(?:{'|'.join([*SMALL, *LARGE])})(?:(?:\s+and\s+|[\s-]+)(?:{'|'.join([*SMALL, *LARGE])}))*\b", re.IGNORECASE
)

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+'’&/-]*[A-Za-z0-9]|[A-Za-z0-9]")
PIECE = re.compile(r"[A-Za-z0-9]+")
MONTHS = {
    "january": "jan", "february": "feb", "march": "mar", "april": "apr", "june": "jun", "july": "jul", "august": "aug",
    "september": "sep", "october": "oct", "november": "nov", "december": "dec",
    "monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
}
# Capitalised words that are not claims about the world.
GENERIC = frozenset("ai api apis ceo cto llm llms gpu gpus cpu ok tv pc".split())
# Words that open a sentence with a capital only because they open it.
OPENERS = frozenset(
    "the a an this that these those it its in on at for from by with without as and but or so yet if when while after "
    "before since because although though however meanwhile also still now then there here they we he she you our "
    "their his her both each all some many most several few no not one two three according today yesterday tomorrow "
    "next last first second third finally later earlier separately together overall instead what who how why where "
    "which to of is are was were will would can could may might should has have had do does did more less another "
    "other new coverage sources reports critics supporters analysts researchers neither either under over between "
    "among during until once whether even only just across against around beyond despite per such than through "
    "toward towards upon within good welcome hello thanks thank let stay keep watch expect look see join that's "
    "here's there's it's what's".split()
)


def numbers_in(text: str) -> set[float]:
    """Every number in the text as a value, so that "$900M", "900 million" and "nine hundred million" are equal."""
    found = set()

    def digits(match: re.Match) -> str:
        value = float(match.group(1).replace(",", "") + (match.group(2) or ""))
        scale = (match.group(3) or match.group(4) or "").lower()
        found.add(value * SCALES.get(scale, 1))
        return " "

    # Numbers in digits are taken out first, so that the "billion" of "4 billion" is not counted again as a word.
    rest = DIGITS.sub(digits, text)
    for match in SPELLED.finditer(rest):
        words = re.findall(r"[a-z]+", match.group().lower())
        # "one" alone is usually a pronoun; "and" joins a number only after hundred or larger.
        for group in _split_at_loose_and(words):
            if group != ["one"]:
                found.add(_value_of(group))
    return found


def _split_at_loose_and(words: list[str]) -> list[list[str]]:
    groups, current = [], []
    for word in words:
        if word != "and":
            current.append(word)
        elif not current or current[-1] not in LARGE:
            groups.append(current)
            current = []
    groups.append(current)
    return [group for group in groups if group]


def _value_of(words: list[str]) -> float:
    total = current = 0.0
    for word in words:
        if word in SMALL:
            current += SMALL[word]
        elif word == "hundred":
            current = max(current, 1) * 100
        else:
            total += max(current, 1) * LARGE[word]
            current = 0
    return total + current


@dataclass
class Pool:
    """The source text a sentence is checked against."""

    numbers: set[float]
    pieces: set[str]

    @classmethod
    def of(cls, texts: list[str | None]) -> "Pool":
        text = "\n".join(part for part in texts if part)
        return cls(numbers_in(text), {piece.lower() for piece in PIECE.findall(text)})

    def __or__(self, other: "Pool") -> "Pool":
        return Pool(self.numbers | other.numbers, self.pieces | other.pieces)

    def has_number(self, value: float) -> bool:
        return any(math.isclose(value, known, rel_tol=1e-9, abs_tol=1e-9) for known in self.numbers)

    def has_piece(self, piece: str) -> bool:
        return piece in self.pieces or piece in GENERIC or MONTHS.get(piece, "") in self.pieces


def unsupported(sentence: str, pool: Pool) -> list[str]:
    """What the sentence states that the source does not contain. An empty list means the sentence passes."""
    problems = [f"number {value:g}" for value in sorted(numbers_in(sentence)) if not pool.has_number(value)]
    for position, token in enumerate(TOKEN.findall(sentence)):
        # A lower-case word claims no name, and a figure such as 1T or 900M was checked as a number above.
        if not any(c.isupper() for c in token) or DIGITS.fullmatch(token):
            continue
        plain_opener = position == 0 and not any(c.isupper() or c.isdigit() for c in token[1:])
        if plain_opener and (token.lower().replace("’", "'") in OPENERS or token.lower().endswith("ly")):
            continue
        # In a joined word such as AI-built or SWE-bench only the capitalised parts are names.
        parts = [part for part in re.split(r"[-/]", token) if any(c.isupper() for c in part)] if position else [token]
        pieces = [piece.lower() for part in parts for piece in PIECE.findall(part) if len(piece) > 1 and any(c.isalpha() for c in piece)]
        if any(not pool.has_piece(piece) for piece in pieces):
            problems.append(f"name {token}")
    return problems
