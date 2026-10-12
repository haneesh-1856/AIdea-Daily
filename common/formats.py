"""The longer episodes made beside the regular one: the podcast (one presenter) and the duo (a host and a guest).

Both are written from the same stories and sources as the regular episode. This module stores them and turns a
written script into the pieces that are spoken."""

import re

from sqlalchemy import Connection, Row, select

from common.db import format_scripts, format_segments
from common.text import sentences

# format -> what it is called on a page, who speaks in it, and its files in the day's folder
FORMATS = {
    "podcast": {"name": "podcast", "label": "one presenter", "speakers": ("PRESENTER",),
                "script": "podcast-script.md", "audio": "podcast-episode.mp3"},
    "duo": {"name": "two-person podcast", "label": "host and guest", "speakers": ("HOST", "GUEST"),
            "script": "duo-script.md", "audio": "duo-episode.mp3"},
}
# Where each speaker's reference recording is named, under [formats.voices] in the settings.
VOICES = {"PRESENTER": "presenter", "HOST": "host", "GUEST": "guest"}
KINDS = ("cold_open", "intro", "stories", "closing")

# The voice model's own expression tags. One at the start of a sentence is a direction for how it is said.
TAGS = ("advertisement", "angry", "chuckle", "clear throat", "cough", "crying", "dramatic", "fear", "gasp", "groan",
        "happy", "laugh", "narration", "sarcastic", "shush", "sigh", "sniff", "surprised", "whispering")
TAG = re.compile(r"\[(?:" + "|".join(TAGS) + r")\]")
MIN_WORDS = 4  # the voice is unsteady on a shorter piece, so a short sentence is said together with its neighbour


def wanted(settings: dict) -> list[str]:
    """The formats switched on in the run's settings. A run started before they existed has none."""
    chosen = settings.get("formats") or {}
    return [name for name in FORMATS if chosen.get(name)]


def begin(conn: Connection, run_id: int, name: str) -> None:
    if name not in scripts_of(conn, run_id):
        conn.execute(format_scripts.insert().values(run_id=run_id, format=name))


def scripts_of(conn: Connection, run_id: int) -> dict[str, Row]:
    return {row.format: row for row in conn.execute(select(format_scripts).where(format_scripts.c.run_id == run_id))}


def update(conn: Connection, run_id: int, name: str, **values) -> None:
    where = (format_scripts.c.run_id == run_id) & (format_scripts.c.format == name)
    conn.execute(format_scripts.update().where(where).values(**values))


def save_plan(conn: Connection, run_id: int, name: str, plan: list[dict]) -> None:
    """Store the plan as empty segments, in order. An earlier plan for the format is replaced."""
    conn.execute(format_segments.delete().where((format_segments.c.run_id == run_id) & (format_segments.c.format == name)))
    conn.execute(
        format_segments.insert(),
        [{"run_id": run_id, "format": name, "position": number, **segment} for number, segment in enumerate(plan, 1)],
    )


def segments_of(conn: Connection, run_id: int, name: str) -> list[Row]:
    where = (format_segments.c.run_id == run_id) & (format_segments.c.format == name)
    return list(conn.execute(select(format_segments).where(where).order_by(format_segments.c.position)))


def save_lines(conn: Connection, segment_id: int, lines: list[dict], illustrations: list[str]) -> None:
    conn.execute(format_segments.update().where(format_segments.c.id == segment_id).values(lines=lines, illustrations=illustrations))


def written(segments: list) -> bool:
    """Whether the whole script is there: a script with a segment missing is never checked, spoken or handed over."""
    return bool(segments) and all(segment.lines for segment in segments)


def plain(text: str) -> str:
    """The words of a line, without its expression tags."""
    return re.sub(r"\s+", " ", TAG.sub(" ", text)).strip()


def spoken_words(lines: list[dict] | None, speaker: str | None = None) -> int:
    return sum(len(plain(line["text"]).split()) for line in lines or [] if speaker in (None, line["speaker"]))


def split(text: str) -> list[str]:
    """A line split into the pieces spoken one at a time: its sentences, with an expression tag opening a new piece.

    A piece of under MIN_WORDS words joins the one before it, or the one after it when it opens the line.
    """
    parts = [part.strip() for sentence in sentences(text) for part in re.split(rf"\s+(?={TAG.pattern})", sentence) if part.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and (len(plain(part).split()) < MIN_WORDS or len(plain(merged[-1]).split()) < MIN_WORDS):
            merged[-1] += " " + part
        else:
            merged.append(part)
    return merged


def pieces(segments: list) -> list[dict]:
    """Every piece to speak, in order: who says it, the text, whether it is a reaction, and where it stands."""
    found, turn = [], 0
    for segment in segments:
        for place, line in enumerate(segment.lines or []):
            turn += 1
            for number, text in enumerate(split(line["text"])):
                found.append({
                    "speaker": line["speaker"], "turn": turn, "text": text,
                    # A reaction is a piece the script gave an expression tag, or one that is exclaimed.
                    "reaction": bool(TAG.search(text)) or text.rstrip("\"'”’").endswith("!"),
                    "opens_segment": place == 0 and number == 0,
                })
    return found
