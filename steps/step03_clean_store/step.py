"""Step 3, Clean and store: turn raw entries into tidy items and save what is new and relevant."""

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.exc import SQLAlchemyError

from common import db, items, runlog
from common.report import step_folder, write_report
from common.settings import ROOT, database_url

STEP = 3
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|source$)")
HREF = re.compile(r"""href=["'](https?://[^"']+)["']""")
SUMMARY_LIMIT = 1500
COUNTS = ("raw", "too_old", "off_topic", "kept", "new")


class CleanError(Exception):
    """The step could not run. The message says why."""


@dataclass
class CleanResult:
    run_id: int
    run_date: date
    state: str  # stored, already_done
    kept: int
    new: int
    report: Path


def canonical_url(url: str) -> str:
    """Normalise a URL so the same article from two sources compares equal."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)])
    # A trailing slash or a stray backslash (seen on Hacker News submissions) does not make a different article.
    return urlunsplit(("https", host, parts.path.rstrip("/\\"), query, ""))


def clean_text(raw: str | None, limit: int | None = None) -> str | None:
    if not raw:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()[:limit] or None


def about_ai_pattern(collect: dict, *, strict: bool = False) -> re.Pattern:
    """Matches a word or phrase that marks an entry as being about AI: the AI keywords, and the words of `also_keep`.

    A keyword may be followed by a hyphen or a digit, which the shared whole-word pattern does not allow: "GPT-6",
    "AI-generated" and "Qwen3" are about AI. On 7 to 9 October 2026 that rule dropped "AI-assisted proof of optimal
    packing for 11 squares" and three other Hacker News stories. A run started before `also_keep` existed has none.

    The strict pattern, for a feed marked strict, leaves out the words of `not_enough_alone`: "model" and "agent" have
    everyday meanings, and on 19 October 2026 "Tesla and Porsche unveil new models" came in from Semafor's feed.
    """
    phrases = [*collect["ai_keywords"], *collect.get("also_keep", [])]
    if strict:
        loose = {word.lower() for word in collect.get("not_enough_alone", [])}
        phrases = [phrase for phrase in phrases if phrase.lower() not in loose]
    words = "|".join(re.escape(phrase) for phrase in sorted(phrases, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])({words})(?![^\W\d])", re.IGNORECASE)


def clean(
    entries: list[dict], collect: dict, fetched_at: datetime, source_links: frozenset[str] = frozenset()
) -> tuple[list[dict], dict[str, dict]]:
    """Returns the items worth storing, and per source how many entries were raw, too old, off topic and kept.

    source_links are the cleaned links of articles already stored from the AI sources.
    """
    cutoff = fetched_at - timedelta(days=collect["max_age_days"])
    keywords = about_ai_pattern(collect)
    strict_keywords = about_ai_pattern(collect, strict=True)
    # A general entry that links to an article one of the AI sources published is about AI, whatever its title says.
    about_ai = source_links | {canonical_url(entry["url"]) for entry in entries if not entry["general"]}
    kept, tally = [], {}
    for entry in entries:
        counts = tally.setdefault(entry["source"], dict.fromkeys(COUNTS, 0))
        counts["raw"] += 1
        title = clean_text(entry["title"])
        if not title:
            continue
        # An entry with no date is kept: dates come from the source and are never guessed.
        published = datetime.fromisoformat(entry["published_at"]) if entry["published_at"] else None
        if published and published < cutoff:
            counts["too_old"] += 1
            continue
        summary = clean_text(entry.get("summary"), SUMMARY_LIMIT)
        link = canonical_url(entry["url"])
        # A strict feed covers everything (Semafor: politics, war, business), and its summaries mention AI in
        # passing ("These days he's using AI to expand his work"), so only its title is read. An entry stored
        # before strict existed has no such field.
        if entry.get("strict"):
            on_topic = strict_keywords.search(title)
        else:
            on_topic = keywords.search(f"{title} {summary or ''}")
        if entry["general"] and link not in about_ai and not on_topic:
            counts["off_topic"] += 1
            continue
        counts["kept"] += 1
        kept.append({
            "source": entry["source"],
            "kind": entry["kind"],
            "title": title,
            "url": entry["url"],
            "canonical_url": link,
            # Step 4 uses these: an item that links to another item's article is about the same story.
            "links": sorted({canonical_url(href) for href in HREF.findall(entry.get("summary") or "")} - {link}),
            "summary": summary,
            "published_at": published,
            "fetched_at": fetched_at,
            "points": entry.get("points"),
            "comments": entry.get("comments"),
            "discussion_url": entry.get("discussion_url"),
        })
    return kept, tally


def clean_store(run_date: date, *, root: Path = ROOT) -> CleanResult:
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"
    entries_file = step_folder(root, run_date, STEP - 1) / "entries.json"

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if STEP - 1 not in done or not entries_file.exists():
                raise CleanError(f"There are no fetched entries for {run_date}. Run step 2 first.")
            if STEP in done:
                return CleanResult(run.id, run_date, "already_done", 0, 0, report)

            fetched = json.loads(entries_file.read_text(encoding="utf-8"))
            # The run's frozen settings are used, not the files, which may have changed since step 1.
            kept, tally = clean(
                fetched["entries"], run.settings["collect"], datetime.fromisoformat(fetched["fetched_at"]),
                items.source_links(conn),
            )

            runlog.begin_step(conn, run.id, STEP)
            for item in kept:
                tally[item["source"]]["new"] += items.upsert(conn, run.id, item)
            total = {key: sum(counts[key] for counts in tally.values()) for key in COUNTS}
            summary = f"{total['raw']} raw entries, {total['kept']} kept, {total['new']} new"
            runlog.finish_step(conn, run.id, STEP, detail=summary)
    except SQLAlchemyError as exc:
        raise CleanError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    write_report(root, run_date, STEP, _report_lines(run_date, run.settings["collect"], summary, tally, total))
    return CleanResult(run.id, run_date, "stored", total["kept"], total["new"], report)


def _report_lines(run_date: date, collect: dict, summary: str, tally: dict, total: dict) -> list[str]:
    def row(name: str, counts: dict) -> str:
        return f"| {name} | " + " | ".join(str(counts[key]) for key in COUNTS) + " |"

    return [
        f"# Step 3, Clean and store: {run_date.isoformat()}",
        "",
        f"{summary}.",
        "",
        f"- **Too old:** published more than {collect['max_age_days']} days before the fetch.",
        "- **Off topic:** from Hacker News or a general feed, and matching none of the AI keywords; from a strict feed,"
        " a title that names AI only by a word from not_enough_alone, or not at all.",
        "- **Kept:** passed both filters.",
        "- **New:** kept and not already stored. The rest of the kept items were stored on an earlier run.",
        "",
        "| Source | Raw | Too old | Off topic | Kept | New |",
        "| --- | --- | --- | --- | --- | --- |",
        *(row(name, counts) for name, counts in tally.items()),
        row("**Total**", total),
    ]
