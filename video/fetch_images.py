"""Fetch each story's lead image: the preview picture (og:image) its source pages name for sharing.

The pictures belong to the publishers, so the video credits each one on screen. They are fine for watching the
video privately; check the rights before publishing it. `build_timeline.py --images generated` leaves them out.

    .venv\\Scripts\\python.exe video\\fetch_images.py 2026-10-16
"""

import io
import json
import re
import sqlite3
import sys
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 ai-news-agent/0.1"}
META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
WANTED = ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src")
SMALLEST = 600  # pixels wide; anything smaller is an icon or a logo
# A card the site draws from text, or its logo: GitHub's repo card, OpenRouter's price card, "og.png", "logo-white.png".
# Under a title its words clash with the title's, so the story's drawn pictures are used instead.
CARD = re.compile(r"opengraph|og[-_]?image|/og\.(?:png|jpe?g|webp)|logo|default", re.IGNORECASE)
AGGREGATORS = {"Hacker News", "Reddit", "Lobsters"}


def lead_image(html: str) -> str | None:
    for tag in META.findall(html):
        name = re.search(r"(?:property|name)\s*=\s*[\"']([^\"']+)", tag, re.IGNORECASE)
        content = re.search(r"content\s*=\s*[\"']([^\"']+)", tag, re.IGNORECASE)
        if name and content and name.group(1).lower() in WANTED:
            return content.group(1).replace("&amp;", "&")
    return None


def stories_of(conn, day: str) -> list[tuple[int, list[tuple[str, str]]]]:
    run_id = conn.execute("select id from runs where run_date=? order by id desc limit 1", (day,)).fetchone()[0]
    rows = conn.execute(
        """select es.story_id, s.item_ids from episode_stories es join episodes e on e.id = es.episode_id
           join selections s on s.story_id = es.story_id and s.run_id = e.run_id
           where e.run_id = ? and es.form != 'dropped' order by es.position""",
        (run_id,),
    ).fetchall()
    out = []
    for story_id, item_ids in rows:
        items = [conn.execute("select source, url from items where id=?", (i,)).fetchone() for i in json.loads(item_ids)]
        out.append((story_id, [i for i in items if i]))
    return out


def main(day: str) -> None:
    folder = Path(__file__).parent / "cache" / day / "images"
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ROOT / "data" / "local.db")
    found, seen = {}, {}
    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for story_id, items in stories_of(conn, day):
            for source, url in items:
                try:
                    page = client.get(url)
                    src = lead_image(page.text) if page.status_code == 200 else None
                    if not src:
                        continue
                    src = str(httpx.URL(str(page.url)).join(src))
                    if CARD.search(src):
                        continue
                    picture = Image.open(io.BytesIO(client.get(src).content)).convert("RGB")
                except Exception as exc:  # one page that will not load does not stop the rest
                    print(f"  story {story_id}: {url}: {type(exc).__name__}")
                    continue
                if picture.width < SMALLEST:
                    continue
                if picture.width > 1920:
                    picture = picture.resize((1920, round(picture.height * 1920 / picture.width)), Image.LANCZOS)
                file = folder / f"article-{story_id}.jpg"
                picture.save(file, quality=88)
                # A link aggregator did not make the picture: credit the site it links to.
                credit = httpx.URL(str(page.url)).host.removeprefix("www.") if source in AGGREGATORS else source
                found[story_id] = {"file": file.name, "credit": credit, "src": src}
                seen.setdefault(src, []).append(story_id)
                break
    # A picture shared by several stories is the site's default card, not about the story.
    for src, story_ids in seen.items():
        if len(story_ids) > 1:
            for story_id in story_ids:
                (folder / found.pop(story_id)["file"]).unlink(missing_ok=True)
    (folder.parent / "article-images.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
    print(f"{len(found)} lead images -> {folder}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-10-16")
