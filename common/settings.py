"""Loads and validates the settings files. A bad setting stops the run before any work."""

import os
import tomllib
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
FEED_KINDS = {"primary", "press", "newsletter"}
LONGEST_EPISODE = 120  # minutes
LENGTH_TIERS = ("long", "medium", "short")
MODEL_PROVIDERS = {"anthropic"}
VOICE_ENGINES = {"chatterbox", "chatterbox-turbo"}
MODEL_EFFORTS = {"", "low", "medium", "high", "xhigh", "max"}
# Settings checked by kind: section -> keys. A dotted key is a value inside a sub-table.
WHOLE_NUMBERS = {
    "group": ["max_judge_pairs"],
    "select": ["max_stories", "max_sources", "rumour_min_points"],
    "write": ["max_source_words", "max_story_words"],
    "episode": ["words_per_minute", "headlines"],
    "lengths": [*(f"{tier}_words" for tier in LENGTH_TIERS), "quick_words"],
}
NUMBERS = {
    "group": ["merge_at", "judge_from"],
    "score": [
        "traction_max",
        *(f"weights.{name}" for name in ("importance", "outlet", "primary", "hn_points", "hn_comments", "staying", "focus")),
        *(f"rubric.{name}" for name in (
            "immediate_value", "ai_impact", "audience_relevance", "magnitude", "practical_impact", "novelty", "credibility",
            "future_significance",
        )),
    ],
    "select": ["min_score", "short_day_minutes", "watch_from", "culture_max"],
    "check": ["hold_above"],
    "lengths": [f"{tier}_from" for tier in LENGTH_TIERS],
}


class SettingsError(Exception):
    """A settings file is missing or wrong. The message says what to fix."""


def _read_toml(path: Path) -> dict:
    if not path.exists():
        raise SettingsError(f"{path.name} is missing from {path.parent}")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SettingsError(f"{path.name} is not valid TOML: {exc}") from exc


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _number(value, minimum: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= minimum


def _word_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(word, str) and word.strip() for word in value)


def load(root: Path = ROOT) -> dict:
    """Read sources.toml and settings.toml, and report every problem found at once."""
    sources = _read_toml(root / "sources.toml")
    run = _read_toml(root / "settings.toml")
    problems = []

    feeds = sources.get("feed", [])
    if not feeds:
        problems.append("sources.toml lists no [[feed]] entries")
    for number, feed in enumerate(feeds, 1):
        label = feed.get("name") or f"feed #{number}"
        for key in ("name", "kind", "url"):
            if not feed.get(key):
                problems.append(f"sources.toml: {label} has no {key}")
        if feed.get("kind") and feed["kind"] not in FEED_KINDS:
            problems.append(f"sources.toml: {label} has kind '{feed['kind']}'; use one of {sorted(FEED_KINDS)}")
        if feed.get("type") == "sitemap" and not feed.get("path_prefix"):
            problems.append(f"sources.toml: {label} is a sitemap and needs a path_prefix")
        if feed.get("type") == "listing" and not feed.get("only"):
            problems.append(f"sources.toml: {label} is a listing and needs `only`, the type of entry to keep")

    collect = sources.get("settings", {})
    for key in ("max_age_days", "hn_min_points"):
        if not _positive_int(collect.get(key)):
            problems.append(f"sources.toml: [settings] {key} must be a whole number above zero")
    if not collect.get("ai_keywords"):
        problems.append("sources.toml: [settings] ai_keywords is empty")
    if not _word_list(collect.get("also_keep", [])):
        problems.append("sources.toml: [settings] also_keep must be a list of words or phrases")

    episode = run.get("episode", {})
    if not (_positive_int(episode.get("length_minutes")) and episode["length_minutes"] <= LONGEST_EPISODE):
        problems.append(f"settings.toml: [episode] length_minutes must be a whole number from 1 to {LONGEST_EPISODE}")

    retention = run.get("retention", {})
    for key in ("article_text_days", "audio_days"):
        if not _positive_int(retention.get(key)):
            problems.append(f"settings.toml: [retention] {key} must be a whole number above zero")

    model = run.get("model", {})
    if bool(model.get("provider")) != bool(model.get("name")):
        problems.append("settings.toml: [model] needs both provider and name, or neither")
    if model.get("provider") and model["provider"] not in MODEL_PROVIDERS:
        problems.append(f"settings.toml: [model] provider must be one of {sorted(MODEL_PROVIDERS)}")
    if model.get("effort", "") not in MODEL_EFFORTS:
        problems.append(f"settings.toml: [model] effort must be one of {sorted(MODEL_EFFORTS)}")
    for key in ("price_in", "price_out"):
        if not _number(model.get(key, 0), minimum=0):
            problems.append(f"settings.toml: [model] {key} must be a number, zero or above")

    for section, keys in WHOLE_NUMBERS.items():
        for key in keys:
            if not _positive_int(run.get(section, {}).get(key)):
                problems.append(f"settings.toml: [{section}] {key} must be a whole number above zero")
    for section, keys in NUMBERS.items():
        for key in keys:
            value = run.get(section, {})
            for part in key.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if not _number(value, minimum=0):
                problems.append(f"settings.toml: [{section}] {key} must be a number, zero or above")

    group = run.get("group", {})
    if _number(group.get("merge_at"), 0) and _number(group.get("judge_from"), 0):
        if not group["judge_from"] <= group["merge_at"] <= 1:
            problems.append("settings.toml: [group] needs judge_from <= merge_at <= 1")
    if not group.get("embedding_model"):
        problems.append("settings.toml: [group] embedding_model is empty")

    lengths = run.get("lengths", {})
    if all(_number(lengths.get(f"{tier}_from"), 0) for tier in LENGTH_TIERS):
        if not lengths["long_from"] >= lengths["medium_from"] >= lengths["short_from"]:
            problems.append("settings.toml: [lengths] needs long_from >= medium_from >= short_from")

    score = run.get("score", {})
    if not _word_list(score.get("focus", [])):
        problems.append("settings.toml: [score] focus must be a list of words or phrases")
    topics = run.get("topics", {})
    if not topics or not all(_word_list(words) and words for words in topics.values()):
        problems.append("settings.toml: [topics] needs at least one topic, each with a list of words")

    voice = run.get("voice", {})
    if not isinstance(voice.get("enabled"), bool):
        problems.append("settings.toml: [voice] enabled must be true or false")
    for key in ("reference", "python"):
        if not voice.get(key):
            problems.append(f"settings.toml: [voice] {key} is empty")
    if voice.get("engine") not in VOICE_ENGINES:
        problems.append(f"settings.toml: [voice] engine must be one of {sorted(VOICE_ENGINES)}")
    for key in ("exaggeration", "cfg_weight", "temperature"):
        if not _number(voice.get(key), minimum=0):
            problems.append(f"settings.toml: [voice] {key} must be a number, zero or above")
    if not (_number(voice.get("speed"), minimum=0.7) and voice["speed"] <= 1.4):
        problems.append("settings.toml: [voice] speed must be between 0.7 and 1.4")
    for key in ("phrase", "sentence", "part", "headline", "story", "longest_phrase"):
        if not _number(voice.get("pauses", {}).get(key), minimum=0):
            problems.append(f"settings.toml: [voice.pauses] {key} must be a number, zero or above")
    if not all(isinstance(said, str) and said.strip() for said in voice.get("say", {}).values()):
        problems.append("settings.toml: [voice.say] every entry must be a word and the way to say it")

    longer = run.get("formats", {})
    for key in ("podcast", "duo"):
        if not isinstance(longer.get(key), bool):
            problems.append(f"settings.toml: [formats] {key} must be true or false")
    if not longer.get("show_name"):
        problems.append("settings.toml: [formats] show_name is empty")
    for key in ("min_minutes", "speaking_pace"):
        if not _positive_int(longer.get(key)):
            problems.append(f"settings.toml: [formats] {key} must be a whole number above zero")
    for key in ("presenter", "host", "guest"):
        if not longer.get("voices", {}).get(key):
            problems.append(f"settings.toml: [formats.voices] {key} is empty")
    for key in ("sentence", "paragraph", "turn", "reaction", "segment"):
        if not _number(longer.get("pauses", {}).get(key), minimum=0):
            problems.append(f"settings.toml: [formats.pauses] {key} must be a number, zero or above")

    if problems:
        raise SettingsError("\n".join(problems))
    return {
        "feeds": feeds,
        "collect": collect,
        "episode": episode,
        "retention": retention,
        "model": model,
        "group": group,
        "score": score,
        "topics": topics,
        "select": run["select"],
        "lengths": lengths,
        "write": run["write"],
        "check": run["check"],
        "voice": voice,
        "formats": longer,
    }


def database_url(root: Path = ROOT) -> str:
    """The database to use: DATABASE_URL from the environment or .env, else a local file."""
    url = os.environ.get("DATABASE_URL") or dotenv_values(root / ".env").get("DATABASE_URL")
    if not url:
        return f"sqlite:///{(root / 'data' / 'local.db').as_posix()}"
    # Supabase hands out postgresql:// addresses; SQLAlchemy needs the driver named.
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url
