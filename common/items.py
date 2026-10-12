"""Stored news items."""

from sqlalchemy import Connection, select

from common.db import item_links, items


def source_links(conn: Connection) -> frozenset[str]:
    """The cleaned links of every stored article that came from a source's own feed, not from Hacker News."""
    return frozenset(conn.execute(select(items.c.canonical_url).where(items.c.kind != "traction")).scalars())


def upsert(conn: Connection, run_id: int, item: dict) -> bool:
    """Insert an item, or refresh its traction numbers if it is already stored. Returns True if it was new."""
    where = (items.c.source == item["source"]) & (items.c.canonical_url == item["canonical_url"])
    if conn.execute(select(items.c.id).where(where)).first():
        conn.execute(items.update().where(where).values(points=item.get("points"), comments=item.get("comments")))
        return False
    values = {key: value for key, value in item.items() if key != "links"}
    item_id = conn.execute(items.insert().values(run_id=run_id, **values)).inserted_primary_key[0]
    if item.get("links"):
        conn.execute(item_links.insert(), [{"item_id": item_id, "canonical_url": link} for link in item["links"]])
    return True
