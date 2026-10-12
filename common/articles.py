"""The full text of items' articles, kept for a limited time."""

from datetime import datetime

from sqlalchemy import Connection, Row, select

from common.db import articles


def get(conn: Connection, item_id: int) -> Row | None:
    return conn.execute(select(articles).where(articles.c.item_id == item_id)).first()


def save(conn: Connection, item_id: int, status: str, text: str | None, fetched_at: datetime) -> None:
    """Store the result of reading an item's article, replacing an earlier result for the same item."""
    conn.execute(articles.delete().where(articles.c.item_id == item_id))
    conn.execute(
        articles.insert().values(
            item_id=item_id, status=status, text=text, words=len(text.split()) if text else 0, fetched_at=fetched_at
        )
    )


def clear_old_text(conn: Connection, before: datetime) -> int:
    """Empty the text of articles read before the given time. The row stays, so it is known the article was read."""
    result = conn.execute(
        articles.update().where((articles.c.fetched_at < before) & articles.c.text.is_not(None)).values(text=None)
    )
    return result.rowcount
