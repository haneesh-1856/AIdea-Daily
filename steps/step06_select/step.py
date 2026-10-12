"""Step 6, Select: choose what makes today's episode and gather the text to write it from."""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from sqlalchemy.exc import SQLAlchemyError

from common import articles, db, episodes, runlog, scores, selections
from common.report import step_folder, write_report
from common.settings import ROOT, database_url

STEP = 6
USER_AGENT = "ai-news-agent/0.1 (personal feed reader)"
ROBOTS_NAME = "ai-news-agent"
TIMEOUT = 20
MIN_ARTICLE_WORDS = 80  # less than this is a paywall notice, a cookie wall or a stub, not an article
REFUSALS = {401, 402, 403, 429, 451}
NOT_FOR_TODAY = ("WATCH", "SKIP")  # the editor's action levels that keep a story out of the episode
KIND_ORDER = {"primary": 0, "press": 1, "newsletter": 2, "traction": 3}
CORRECTION = re.compile(
    r"\b(correction|corrects|corrected|retracts?|retracted|retraction|walks? back|walked back|withdraws|withdrawn|"
    r"we got it wrong|erratum)\b",
    re.IGNORECASE,
)


class SelectError(Exception):
    """The step could not run. The message says why."""


@dataclass
class SelectResult:
    run_id: int
    run_date: date
    state: str  # selected, already_done
    stories: int
    articles_read: int
    report: Path


@dataclass
class Choice:
    story_id: int
    title: str
    score: float
    kind: str  # new, update, correction
    label: str  # confirmed, reported, rumour
    sources: list  # the items to write from, most authoritative first
    first_seen: date | None = None  # set when the story began on an earlier day and is only now in an episode
    fill: str | None = None  # how it came in when not by the final list: recovered, brief, culture, know, watch


def get(url: str) -> httpx.Response:
    return httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True)


def text_words(row) -> int:
    """How many words there are to write from for one source: its article if it was read, else its description."""
    return row.article_words if row.article_status == "ok" else len((row.summary or "").split())


def label_of(found: list) -> str:
    """Confirmed needs a primary source; reported means press or analysts only; anything else is a rumour."""
    kinds = {row.kind for row in found}
    if "primary" in kinds:
        return "confirmed"
    return "reported" if kinds & {"press", "newsletter"} else "rumour"


def pick_sources(found: list, limit: int) -> list:
    """One item per source, primary source first, never the same article twice."""
    picked, sources_seen, links_seen = [], set(), set()
    for row in sorted(found, key=lambda row: (KIND_ORDER.get(row.kind, 9), row.id)):
        if row.source in sources_seen or row.canonical_url in links_seen:
            continue
        sources_seen.add(row.source)
        links_seen.add(row.canonical_url)
        picked.append(row)
    return picked[:limit]


# How a story that came in after the final list is marked in `selections.fill`, from its place in the lineup.
PHASE_FILLS = {"recovered": "recovered", "brief": "brief", "culture": "culture"}


def final_of(ranked: list) -> dict:
    """{story id: its place in the editor's lineup}, empty when step 5 made none.

    The lineup is the final list (phase 1), then the stories the recovery pass brought back (phase 2), then the
    lighter-side stories (phase 3). A run scored before the later passes existed has only the final list.
    """
    found = {}
    for row in ranked:
        rating = row.signals.get("rating") or {}
        entry = rating.get("lineup") or rating.get("final")
        if entry:
            found[row.story_id] = entry
    return found


def choose(ranked: list, by_story: dict, run_date: date, covered: tuple[set, set], settings: dict,
           last_day: date | None = None) -> tuple[list[Choice], list]:
    """Returns the shortlist in rank order, and the stories that scored enough but were left out, each with the reason.

    `last_day` is the date of the episode before this one."""
    covered_stories, covered_threads = covered
    limits = settings["select"]
    # The minimum score is on the scale of the editor's score. When no story was rated (no model is chosen) it
    # cannot be applied, and the top stories by evidence are taken instead.
    rated = any(row.signals.get("rating") for row in ranked)
    # The editor's final list (step 5) decides what is in the episode and in what order. sorted() keeps the
    # stories not on it in score order behind it.
    final = final_of(ranked)
    if final:
        ranked = sorted(ranked, key=lambda row: final[row.story_id]["rank"] if row.story_id in final else len(ranked) + 1)
    chosen, left_out, passed_over = [], [], []
    # Stories the recovery pass merged into one on the list lend that story their sources.
    merged: dict[int, list[int]] = {}
    for row in ranked:
        into = ((row.signals.get("rating") or {}).get("recovery") or {}).get("into")
        if into in final:
            merged.setdefault(into, []).append(row.story_id)

    def facts(row) -> tuple:
        own = by_story[row.story_id]
        found = own + [item for other in merged.get(row.story_id, ()) for item in by_story[other]]
        today = [item for item in found if item.placed_on == run_date]
        began = min(item.placed_on for item in own)
        seen_before = row.story_id in covered_stories
        if any(CORRECTION.search(item.title) for item in today) and (seen_before or row.thread_id in covered_threads):
            kind = "correction"
        else:
            kind = "update" if seen_before else "new"
        return found, today, began, kind, label_of(found)

    def refusal(row, found: list, today: list, began: date, kind: str, label: str) -> str | None:
        """Why a story that is otherwise wanted may not be in today's episode, or None when it may."""
        if (row.signals.get("rating") or {}).get("stale"):
            return f"old news: it reports something that happened more than {settings['collect']['max_age_days']} days ago"
        # A story from an earlier day that was never in an episode needs real new coverage today: two outlets
        # writing about it today, or the organisation itself. One late mention does not make it today's news.
        # A story first seen for the last episode is given this one more: it may have arrived too late for that
        # one, or been held out of it, and should not be lost at the boundary between two days.
        if kind == "new" and began < (last_day or run_date):
            outlets_today = {item.source for item in today if item.kind != "traction"}
            if len(outlets_today) < 2 and not any(item.kind == "primary" for item in today):
                return f"an older story, first seen {began.isoformat()}, with only a late mention today"
        # "Rumour" only means that no feed followed here wrote about it: often it is a real article from an outlet
        # outside the feeds, posted to Hacker News. So when the model has rated the story, its score decides, and
        # it is told as unconfirmed. The points rule is the guard only when there is no rating to go by.
        if label == "rumour" and not row.signals.get("rating") and row.signals["hn_points"] < limits["rumour_min_points"]:
            return f"a rumour with fewer than {limits['rumour_min_points']} Hacker News points"
        if sum(choice.kind != "correction" for choice in chosen) >= limits["max_stories"]:
            return f"past the limit of {limits['max_stories']} stories for one episode"
        return None

    def take(row, found: list, today: list, began: date, kind: str, label: str, fill: str | None = None) -> None:
        # An update or correction is written from today's items only; what was said before is given to the
        # writer separately.
        sources = pick_sources(found if kind == "new" else today, limits["max_sources"])
        chosen.append(Choice(row.story_id, row.title, row.total, kind, label, sources, began if kind == "new" and began < run_date else None, fill))

    for row in ranked:
        found, today, began, kind, label = facts(row)
        if kind != "correction":
            rating = row.signals.get("rating") or {}
            # The floor is for the final list. A story a later pass brought in was chosen on its own terms.
            if rated and row.total < limits["min_score"] and (final.get(row.story_id) or {}).get("phase", 1) == 1:
                if row.story_id in final:
                    left_out.append((row.title, row.total, f"on the editor's list, but under the floor of {limits['min_score']:g}"))
                continue
            if final and row.story_id not in final:
                passed_over.append(row)
                continue
            # Without a final list (its request failed) the editor's action level decides instead.
            if not final and rating.get("action") in NOT_FOR_TODAY:
                continue
            why = refusal(row, found, today, began, kind, label)
            if why:
                left_out.append((row.title, row.total, why))
                continue
        take(row, found, today, began, kind, label, PHASE_FILLS.get((final.get(row.story_id) or {}).get("as")))

    # A short day: when the editor's list makes an episode under `short_day_minutes`, it is filled from the stories
    # the editor rated but passed over. First those it marked Know today, then those it marked Watch that score
    # `watch_from` or more, which are told briefly in a segment of their own. A story marked Skip is never added.
    # It stops when the episode, at the stories' usual lengths, reaches `short_day_minutes`.
    def minutes() -> float:
        return episodes.planned_minutes([(choice.score, choice.fill) for choice in chosen], settings)

    if final and episodes.short_day([(choice.score, None) for choice in chosen], settings):
        # A story the recovery pass already looked at and left out stays out: this only fills when that pass did not run.
        action = lambda row: None if (row.signals.get("rating") or {}).get("recovery") else (row.signals.get("rating") or {}).get("action")  # noqa: E731
        wanted = {"know": lambda row: action(row) == "KNOW TODAY",
                  "watch": lambda row: action(row) == "WATCH" and row.total >= limits.get("watch_from", 0)}
        for fill in wanted:
            for row in [row for row in passed_over if wanted[fill](row)]:
                if minutes() >= limits["short_day_minutes"]:
                    break
                passed_over.remove(row)
                found, today, began, kind, label = facts(row)
                why = refusal(row, found, today, began, kind, label)
                if why:
                    left_out.append((row.title, row.total, why))
                else:
                    take(row, found, today, began, kind, label, fill)
    left_out += [
        (row.title, row.total, f"the editor left it out: {row.signals['rating']['near_miss']}")
        for row in passed_over if (row.signals.get("rating") or {}).get("near_miss")
    ]
    return chosen, left_out


class Reader:
    """Reads article pages, asking each site's robots.txt first. A site that refuses is not forced."""

    def __init__(self):
        self.robots: dict[str, RobotFileParser] = {}

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        site = f"{parts.scheme}://{parts.netloc}"
        if site not in self.robots:
            rules = RobotFileParser()
            response = get(f"{site}/robots.txt")
            if response.status_code in (401, 403):
                rules.disallow_all = True
            elif response.status_code >= 400:
                rules.allow_all = True
            else:
                rules.parse(response.text.splitlines())
            self.robots[site] = rules
        return self.robots[site].can_fetch(ROBOTS_NAME, url)

    @staticmethod
    def _page(url: str) -> httpx.Response:
        """One request, and one more if the first broke off or the server erred. A refusal is never asked twice."""
        try:
            response = get(url)
        except httpx.HTTPError:
            return get(url)
        return get(url) if response.status_code >= 500 else response

    def read(self, url: str) -> tuple[str, str | None]:
        """Returns (status, text). The status is ok, refused, no text or failed."""
        try:
            if not self.allowed(url):
                return "refused", None
            response = self._page(url)
        except httpx.HTTPError:
            return "failed", None
        if response.status_code in REFUSALS:
            return "refused", None
        if response.status_code >= 400:
            return "failed", None
        text = trafilatura.extract(response.text, include_comments=False, include_tables=False, favor_precision=True)
        if not text or len(text.split()) < MIN_ARTICLE_WORDS:
            return "no text", None
        return "ok", text


def select(run_date: date, *, root: Path = ROOT, now: datetime | None = None) -> SelectResult:
    now = now or datetime.now(timezone.utc)
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if STEP - 1 not in done:
                raise SelectError(f"There are no scores for {run_date}. Run step 5 first.")
            if STEP in done:
                return SelectResult(run.id, run_date, "already_done", 0, 0, report)
            runlog.begin_step(conn, run.id, STEP)

            # The run's frozen settings are used, not the files.
            ranked = scores.ranked(conn, run.id)
            by_story = scores.items_of(conn, [row.story_id for row in ranked])
            before = runlog.last_before(conn, run.run_date)
            chosen, left_out = choose(
                ranked, by_story, run.run_date, selections.covered_before(conn, run.run_date), run.settings,
                before.run_date if before else None,
            )
            wanted = {item.id: item for choice in chosen for item in choice.sources}
            # An article read on an earlier run, with its text still kept, is not read again.
            have = {item_id for item_id in wanted if (old := articles.get(conn, item_id)) and old.status == "ok" and old.text}

        # No transaction is open while pages are read.
        reader = Reader()
        to_read = [item for item_id, item in wanted.items() if item_id not in have]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda item: reader.read(item.url), to_read))

        with engine.begin() as conn:
            for item, (status, text) in zip(to_read, results):
                articles.save(conn, item.id, status, text, now)

            # A source with neither an article nor a description gives nothing to write from, so it is not
            # named as a source; a story left with no text at all cannot be written and is left out.
            detail, writable = {}, []
            for choice in chosen:
                found = selections.sources(conn, [item.id for item in choice.sources])
                detail[choice.story_id] = found
                usable = [row for row in found if text_words(row) > 0]
                if usable:
                    choice.sources = usable
                    writable.append(choice)
                else:
                    left_out.append((choice.title, choice.score, "none of its sources could be read, so there is nothing to write from"))
            chosen = writable
            for rank, choice in enumerate(chosen, 1):
                selections.save(
                    conn, run.id, choice.story_id, rank, choice.score, choice.kind, choice.label,
                    [row.id for row in choice.sources], choice.first_seen, choice.fill,
                )
            read_ok = sum(status == "ok" for status, _ in results)
            summary = f"{len(chosen)} stories selected, {read_ok} of {len(to_read)} articles read"
            rated = any(row.signals.get("rating") for row in ranked)
            lines = _report_lines(run_date, summary, chosen, detail, left_out, run.settings["select"], rated, bool(final_of(ranked)))
            runlog.finish_step(conn, run.id, STEP, detail=summary)
    except SQLAlchemyError as exc:
        raise SelectError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    write_report(root, run_date, STEP, lines)
    return SelectResult(run.id, run_date, "selected", len(chosen), read_ok, report)


def _report_lines(run_date: date, summary: str, chosen: list[Choice], detail: dict, left_out: list, limits: dict, rated: bool,
                  edited: bool = False) -> list[str]:
    if edited:
        basis = (f"The episode is the editor's final list from step 5, in the editor's order, up to {limits['max_stories']} stories. "
                 f"A story scoring under {limits['min_score']:g} is left out even when the editor chose it.")
    else:
        basis = (f"There is no editor's final list, so the episode is every story scoring {limits['min_score']:g} or more that the "
                 f"editor did not mark Watch or Skip, up to {limits['max_stories']} stories.")
    said = {"ok": "article read", "refused": "site refused, description used", "no text": "no article text found, description used",
            "failed": "page could not be read, description used"}
    lines = [
        f"# Step 6, Select: {run_date.isoformat()}",
        "",
        f"{summary}.",
        "",
        f"{basis} " + ("The day was short, so it was filled from what the editor passed over, as listed below the table."
                       if any(choice.fill in ("know", "watch") for choice in chosen) else "Nothing is added to reach a number."),
        *([] if rated else ["", "**No story was rated for importance (no model is chosen), so the minimum score was not applied** "
                            "and the order below rests on outlets and Hacker News traction alone."]),
        "",
        "| Rank | Score | Kind | Label | Story | Sources |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {rank} | {choice.score:g} | {choice.kind} | {choice.label} | {choice.title.replace('|', '/')} | {len(choice.sources)} |"
        for rank, choice in enumerate(chosen, 1)
    ]
    later = {"recovered": "brought back by the recovery pass (phase 2), as a full segment",
             "brief": "brought back by the recovery pass (phase 2), as a quick brief",
             "culture": "chosen for the lighter side (phase 3)"}
    if any(choice.fill in later for choice in chosen):
        lines += ["", "After the final list, the editor's later passes added:", ""]
        lines += [f"- {choice.title} ({choice.score:g}): {later[choice.fill]}" for choice in chosen if choice.fill in later]
    added = {"know": "the editor marked it Know today but left it off the list", "watch": "the editor marked it Watch; told briefly as worth watching"}
    if any(choice.fill in added for choice in chosen):
        lines += ["", f"The editor's list made an episode of under {limits['short_day_minutes']:g} minutes, so these were added:", ""]
        lines += [f"- {choice.title} ({choice.score:g}): {added[choice.fill]}" for choice in chosen if choice.fill in added]
    lines += ["", "## Text gathered for each story", ""]
    for rank, choice in enumerate(chosen, 1):
        lines += [f"**{rank}. {choice.title}**", ""]
        for row in detail[choice.story_id]:
            unused = "" if text_words(row) else " Not used as a source: no text."
            lines.append(f"- {row.source} ({row.kind}): {said[row.article_status]}, {text_words(row)} words.{unused} {row.url}")
        lines.append("")
    if left_out:
        lines += ["## Left out, and why", "", "Stories under the minimum score are not listed; step 5's report has every score.", ""]
        lines += [f"- {title} ({score:g}): {reason}" for title, score, reason in left_out]
    return lines
