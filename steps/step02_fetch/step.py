"""Step 2, Fetch: read every source once and bring back whatever it has."""

import calendar
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit

import feedparser
import httpx
from sqlalchemy.exc import SQLAlchemyError

from common import db, health, runlog
from common.report import step_folder, write_report
from common.settings import ROOT, database_url

STEP = 2
USER_AGENT = "ai-news-agent/0.1 (personal feed reader)"
HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
TIMEOUT = 20  # seconds: the limit for each request, and for a source as a whole


class FetchError(Exception):
    """The fetch could not run or brought back nothing. The message says why."""


@dataclass
class SourceResult:
    name: str
    kind: str
    entries: list[dict]
    error: str | None


@dataclass
class FetchResult:
    run_id: int
    run_date: date
    state: str  # fetched, already_done
    entries: list[dict]
    entries_file: Path
    report: Path


def get(url: str, params: dict | None = None) -> httpx.Response:
    resp = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    return resp


def describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}".rstrip(": ")


def parse_time(stamp: str) -> datetime:
    parsed = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def meta_content(page: str, prop: str) -> str | None:
    match = re.search(rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"', page)
    return html.unescape(match.group(1)) if match else None


def _entry(source: str, kind: str, general: bool, title: str, url: str, published: datetime | None, **extra) -> dict:
    return {
        "source": source,
        "kind": kind,
        "general": general,  # step 3 keeps a general entry only if it matches the AI keywords
        "strict": False,  # and a strict one only if its title does, with more than a word from not_enough_alone
        "title": title,
        "url": url,
        "summary": None,
        "published_at": published.isoformat() if published else None,
        **extra,
    }


def read_feed(feed: dict) -> list[dict]:
    parsed = feedparser.parse(get(feed["url"]).content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"not a readable feed: {parsed.bozo_exception}")

    entries = []
    for item in parsed.entries:
        link, title = item.get("link"), item.get("title")
        if not link or not title:
            continue
        stamp = item.get("published_parsed") or item.get("updated_parsed")
        published = datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc) if stamp else None
        entries.append(
            _entry(feed["name"], feed["kind"], bool(feed.get("general")), title, link, published, summary=item.get("summary"),
                   strict=bool(feed.get("strict")))
        )
    return entries


def read_sitemap(feed: dict, cutoff: datetime) -> list[dict]:
    """For sites without RSS: find recently changed pages in the sitemap, then read each page's own title and date."""
    sitemap = get(feed["url"]).text
    prefix = feed["path_prefix"]
    entries = []
    for loc, lastmod in re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", sitemap):
        path = urlsplit(loc).path
        if not path.startswith(prefix) or path.rstrip("/") == prefix.rstrip("/"):
            continue
        # The age limit is applied here, not only in step 3, so that old pages are never requested.
        modified = parse_time(lastmod)
        if modified < cutoff:
            continue
        try:
            page = get(loc).text
        except httpx.HTTPError:
            continue
        title = meta_content(page, "og:title")
        if not title:
            continue
        # lastmod also changes when an old page is edited, so trust the page's own date when it has one.
        stamp = meta_content(page, "article:published_time")
        published = parse_time(stamp) if stamp else modified
        entries.append(
            _entry(
                feed["name"], feed["kind"], bool(feed.get("general")), title, loc, published,
                summary=meta_content(page, "og:description"), strict=bool(feed.get("strict")),
            )
        )
    return entries


def _plain(value):
    """A value as the page's framework wrote it, [kind, value] at every level, turned back into the plain value."""
    if isinstance(value, dict):
        return {key: _plain(inner) for key, inner in value.items()}
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], int):
        kind, inner = value
        return [_plain(one) for one in inner] if kind == 1 else _plain(inner)
    return value


def read_listing(feed: dict) -> list[dict]:
    """For a page with no feed that carries its own list of entries, as the Vals AI news pages do.

    Each listed entry has a title, a link, a date, a type and the outlet it is from. Only entries of the feed's
    `only` type are kept, and each is credited to the outlet the page names, which is not always the site itself.
    """
    page = get(feed["url"]).text
    match = re.search(r'props="([^"]*&quot;articles&quot;[^"]*)"', page)
    if not match:
        raise ValueError("the page carries no list of articles")
    entries = []
    for item in _plain(json.loads(html.unescape(match.group(1))))["articles"]:
        if not isinstance(item, dict) or item.get("type") != feed["only"]:
            continue
        title, link = item.get("title"), item.get("link")
        if not title or not link:
            continue
        try:
            published = datetime.strptime(item.get("date") or "", "%m/%d/%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            published = None
        entries.append(
            _entry(item.get("source") or feed["name"], feed["kind"], bool(feed.get("general")), title, urljoin(feed["url"], link), published,
                   strict=bool(feed.get("strict")))
        )
    return entries


def read_hacker_news(min_points: int, cutoff: datetime) -> list[dict]:
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>{int(cutoff.timestamp())},points>={min_points}",
        "hitsPerPage": 1000,
    }
    entries = []
    for hit in get(HN_SEARCH, params).json()["hits"]:
        if not hit.get("title"):
            continue
        discussion = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        entries.append(
            _entry(
                "Hacker News", "traction", True, hit["title"], hit.get("url") or discussion,
                datetime.fromtimestamp(hit["created_at_i"], timezone.utc),
                points=hit.get("points"), comments=hit.get("num_comments"), discussion_url=discussion,
            )
        )
    return entries


def _attempt(name: str, kind: str, read: Callable[[], list[dict]]) -> SourceResult:
    try:
        return SourceResult(name, kind, read(), None)
    except Exception as exc:  # whatever goes wrong with one source, the others still count
        return SourceResult(name, kind, [], describe(exc))


def read_all(settings: dict, now: datetime) -> list[SourceResult]:
    collect = settings["collect"]
    cutoff = now - timedelta(days=collect["max_age_days"])
    jobs = []
    for feed in settings["feeds"]:
        if feed.get("type") == "sitemap":
            jobs.append((feed["name"], feed["kind"], lambda feed=feed: read_sitemap(feed, cutoff)))
        elif feed.get("type") == "listing":
            jobs.append((feed["name"], feed["kind"], lambda feed=feed: read_listing(feed)))
        else:
            jobs.append((feed["name"], feed["kind"], lambda feed=feed: read_feed(feed)))
    jobs.append(("Hacker News", "traction", lambda: read_hacker_news(collect["hn_min_points"], cutoff)))

    pool = ThreadPoolExecutor(max_workers=len(jobs))
    futures = [pool.submit(_attempt, *job) for job in jobs]
    wait(futures, timeout=TIMEOUT)
    # A source still going after the limit is abandoned: its result is not waited for.
    pool.shutdown(wait=False, cancel_futures=True)
    return [
        future.result() if future.done() else SourceResult(name, kind, [], f"abandoned after {TIMEOUT} seconds")
        for future, (name, kind, _) in zip(futures, jobs)
    ]


def fetch(run_date: date, *, root: Path = ROOT, now: datetime | None = None) -> FetchResult:
    now = now or datetime.now(timezone.utc)
    url = database_url(root)
    folder = step_folder(root, run_date, STEP)
    entries_file, report = folder / "entries.json", folder / "report.md"

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if STEP - 1 not in done:
                raise FetchError(f"There is no started run for {run_date}. Run step 1 first.")
            # Without the entries file step 3 has nothing to read, so a done step with no file is fetched again.
            if STEP in done and entries_file.exists():
                entries = json.loads(entries_file.read_text(encoding="utf-8"))["entries"]
                return FetchResult(run.id, run_date, "already_done", entries, entries_file, report)
            runlog.begin_step(conn, run.id, STEP)

        # The run's frozen settings are used, not the files, which may have changed since step 1.
        results = read_all(run.settings, now)
        entries = [entry for result in results for entry in result.entries]
        worked = sum(result.error is None for result in results)
        summary = f"{worked} of {len(results)} sources worked, {len(entries)} entries"

        with engine.begin() as conn:
            health.record(
                conn,
                run.id,
                [{"source": r.name, "ok": r.error is None, "entries": len(r.entries), "error": r.error} for r in results],
            )
            streaks = {r.name: health.failing_streak(conn, r.name) for r in results if r.error}
            write_report(root, run_date, STEP, _report_lines(run_date, now, summary, results, streaks))
            if not worked:
                runlog.finish_step(conn, run.id, STEP, "failed", summary)
            else:
                entries_file.write_text(
                    json.dumps({"fetched_at": now.isoformat(), "entries": entries}, ensure_ascii=False, indent=1),
                    encoding="utf-8",
                )
                runlog.finish_step(conn, run.id, STEP, detail=summary)
    except SQLAlchemyError as exc:
        raise FetchError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    if not worked:
        raise FetchError(f"Every source failed, so there is nothing to work with. See {report}")
    return FetchResult(run.id, run_date, "fetched", entries, entries_file, report)


def _report_lines(run_date: date, now: datetime, summary: str, results: list[SourceResult], streaks: dict) -> list[str]:
    lines = [
        f"# Step 2, Fetch: {run_date.isoformat()}",
        "",
        f"{summary}. Fetched at {now.strftime('%Y-%m-%d %H:%M:%S')} UTC.",
        "",
        "Entries are raw: nothing has been filtered by age or topic yet. Step 3 does that.",
        "",
    ]
    failed = [r for r in results if r.error]
    if failed:
        lines += ["## Failed sources", "", "| Source | Failed runs in a row | Error |", "| --- | --- | --- |"]
        lines += [f"| {r.name} | {streaks[r.name]} | {r.error[:200].replace('|', '/')} |" for r in failed]
        lines.append("")
    lines += ["## Every source", "", "| Source | Kind | Result | Entries |", "| --- | --- | --- | --- |"]
    lines += [f"| {r.name} | {r.kind} | {'Failed' if r.error else 'OK'} | {len(r.entries)} |" for r in results]
    return lines
