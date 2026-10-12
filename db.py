"""SQLite store for collected news items."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "news.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    summary       TEXT,
    published_at  TEXT,
    fetched_at    TEXT NOT NULL,
    points        INTEGER,
    comments      INTEGER,
    discussion_url TEXT,
    UNIQUE (source, canonical_url)
);
CREATE INDEX IF NOT EXISTS idx_items_canonical ON items (canonical_url);
CREATE INDEX IF NOT EXISTS idx_items_published ON items (published_at);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_item(conn: sqlite3.Connection, item: dict) -> bool:
    """Insert an item, or refresh its traction numbers. Returns True if it was new."""
    cur = conn.execute(
        "SELECT id FROM items WHERE source = ? AND canonical_url = ?",
        (item["source"], item["canonical_url"]),
    )
    row = cur.fetchone()
    if row:
        conn.execute(
            "UPDATE items SET points = ?, comments = ? WHERE id = ?",
            (item.get("points"), item.get("comments"), row["id"]),
        )
        return False
    conn.execute(
        """INSERT INTO items (source, kind, title, url, canonical_url, summary,
                              published_at, fetched_at, points, comments, discussion_url)
           VALUES (:source, :kind, :title, :url, :canonical_url, :summary,
                   :published_at, :fetched_at, :points, :comments, :discussion_url)""",
        {"summary": None, "points": None, "comments": None, "discussion_url": None, **item},
    )
    return True
