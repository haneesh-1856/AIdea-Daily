"""Small text helpers shared by the steps."""

import re


def phrase_pattern(phrases: list[str]) -> re.Pattern:
    """Matches any of the words or phrases as whole words, in any letter case."""
    words = "|".join(re.escape(phrase) for phrase in sorted(phrases, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])({words})(?![\w-])", re.IGNORECASE)


def sentences(text: str | None) -> list[str]:
    """Split text into sentences. A full stop inside a number or an abbreviation such as U.S. does not end one."""
    if not text or not text.strip():
        return []
    # The split is at the space only, so a closing quote or bracket after the full stop stays with its sentence.
    parts = re.split(r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)]))\s+(?=[\"'“‘(]?[A-Z0-9])", text.strip())
    merged: list[str] = []
    for part in parts:
        # "the U.S. Senate" and "Dr. Lee" were split above; an ending like that is glued back to what follows.
        if merged and re.search(r"(?:\b[A-Z]\.|\b(?:Mr|Mrs|Ms|Dr|St|vs|Inc|Ltd|Co|Corp|No)\.)$", merged[-1]):
            merged[-1] += " " + part
        else:
            merged.append(part)
    return [part.strip() for part in merged if part.strip()]


def word_count(text: str | None) -> int:
    return len(text.split()) if text else 0
