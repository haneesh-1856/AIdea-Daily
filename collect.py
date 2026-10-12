"""Collect AI news from RSS feeds, sitemaps and Hacker News into SQLite.

Usage: python collect.py
"""

import calendar
import html
import re
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx

import db

SOURCES_PATH = Path(__file__).parent / "sources.toml"
USER_AGENT = "ai-news-agent/0.1 (personal feed reader)"
HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|source$)")
SUMMARY_LIMIT = 1500


def canonical_url(url: str) -> str:
    """Normalise a URL so the same article from two sources compares equal."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)])
    return urlunsplit(("https", host, parts.path.rstrip("/"), query, ""))


def clean_text(raw: str | None) -> str | None:
    if not raw:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()[:SUMMARY_LIMIT] or None


def keyword_pattern(settings: dict) -> re.Pattern:
    words = "|".join(re.escape(k) for k in settings["ai_keywords"])
    return re.compile(rf"(?<![\w-])({words})(?![\w-])", re.IGNORECASE)


def describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0]}"


def parse_time(stamp: str) -> datetime:
    parsed = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def get(url: str) -> httpx.Response:
    resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    return resp


def meta_content(page: str, prop: str) -> str | None:
    match = re.search(rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"', page)
    return clean_text(match.group(1)) if match else None


def fetch_sitemap(feed: dict, cutoff: datetime, now: datetime) -> tuple[dict, list[dict], str | None]:
    """For sites without RSS: find recently changed pages in the sitemap, then read each page's own title and date."""
    try:
        sitemap = get(feed["url"]).text
    except httpx.HTTPError as exc:
        return feed, [], describe(exc)

    prefix = feed["path_prefix"]
    items = []
    for loc, lastmod in re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", sitemap):
        path = urlsplit(loc).path
        if not path.startswith(prefix) or path.rstrip("/") == prefix.rstrip("/"):
            continue
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
        if published < cutoff:
            continue
        items.append({
            "source": feed["name"],
            "kind": feed["kind"],
            "title": title,
            "url": loc,
            "canonical_url": canonical_url(loc),
            "summary": meta_content(page, "og:description"),
            "published_at": published.isoformat(),
            "fetched_at": now.isoformat(),
        })
    return feed, items, None


def fetch_feed(feed: dict, cutoff: datetime, now: datetime, keywords: re.Pattern) -> tuple[dict, list[dict], str | None]:
    if feed.get("type") == "sitemap":
        return fetch_sitemap(feed, cutoff, now)
    try:
        resp = get(feed["url"])
    except httpx.HTTPError as exc:
        return feed, [], describe(exc)

    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        return feed, [], f"not a readable feed: {parsed.bozo_exception}"

    items = []
    for entry in parsed.entries:
        link, title = entry.get("link"), clean_text(entry.get("title"))
        if not link or not title:
            continue
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        published = datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc) if stamp else None
        if published and published < cutoff:
            continue
        summary = clean_text(entry.get("summary"))
        if feed.get("general") and not keywords.search(f"{title} {summary or ''}"):
            continue
        items.append({
            "source": feed["name"],
            "kind": feed["kind"],
            "title": title,
            "url": link,
            "canonical_url": canonical_url(link),
            "summary": summary,
            "published_at": published.isoformat() if published else None,
            "fetched_at": now.isoformat(),
        })
    return feed, items, None


def fetch_hacker_news(settings: dict, cutoff: datetime, now: datetime, keywords: re.Pattern) -> tuple[list[dict], str | None]:
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>{int(cutoff.timestamp())},points>={settings['hn_min_points']}",
        "hitsPerPage": 1000,
    }
    try:
        resp = httpx.get(HN_SEARCH, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return [], describe(exc)

    items = []
    for hit in resp.json()["hits"]:
        title = hit.get("title") or ""
        if not keywords.search(title):
            continue
        discussion = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        url = hit.get("url") or discussion
        items.append({
            "source": "Hacker News",
            "kind": "traction",
            "title": title,
            "url": url,
            "canonical_url": canonical_url(url),
            "published_at": datetime.fromtimestamp(hit["created_at_i"], timezone.utc).isoformat(),
            "fetched_at": now.isoformat(),
            "points": hit.get("points"),
            "comments": hit.get("num_comments"),
            "discussion_url": discussion,
        })
    return items, None


def main() -> int:
    config = tomllib.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    settings = config["settings"]
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings["max_age_days"])
    keywords = keyword_pattern(settings)

    with ThreadPoolExecutor(max_workers=8) as pool:
        feed_results = list(pool.map(lambda f: fetch_feed(f, cutoff, now, keywords), config["feed"]))
    hn_items, hn_error = fetch_hacker_news(settings, cutoff, now, keywords)

    results = [(f["name"], items, err) for f, items, err in feed_results]
    results.append(("Hacker News", hn_items, hn_error))

    conn = db.connect()
    total_new = failed = 0
    print(f"{'source':<28}{'recent':>8}{'new':>6}")
    for name, items, error in results:
        if error:
            failed += 1
            print(f"{name:<28}  FAILED  {error[:90]}")
            continue
        new = sum(db.upsert_item(conn, item) for item in items)
        total_new += new
        print(f"{name:<28}{len(items):>8}{new:>6}")
    conn.commit()
    conn.close()

    print(f"\n{total_new} new items, {failed} of {len(results)} sources failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
