"""Stories: the items that are about the same event, and why each was put there."""

from datetime import datetime

from sqlalchemy import Connection, Row, select

from common.db import item_links, items, judge_log, splits, stories, story_items, threads

_COLUMNS = (
    items.c.id, items.c.source, items.c.kind, items.c.title, items.c.summary, items.c.url, items.c.canonical_url,
    items.c.fetched_at,
)


def ungrouped_items(conn: Connection) -> list[Row]:
    """Items that are in no story yet, whatever their age."""
    query = (
        select(*_COLUMNS, story_items.c.story_id)
        .select_from(items.outerjoin(story_items))
        .where(story_items.c.story_id.is_(None))
        .order_by(items.c.id)
    )
    return list(conn.execute(query))


def grouped_items(conn: Connection, since: datetime) -> list[Row]:
    """Items already in a story and fetched at or after the given time."""
    query = (
        select(*_COLUMNS, story_items.c.story_id)
        .select_from(items.join(story_items))
        .where(items.c.fetched_at >= since)
        .order_by(items.c.id)
    )
    return list(conn.execute(query))


def links_of(conn: Connection, item_ids: list[int]) -> dict[int, set[str]]:
    found: dict[int, set[str]] = {}
    for row in conn.execute(select(item_links).where(item_links.c.item_id.in_(item_ids))):
        found.setdefault(row.item_id, set()).add(row.canonical_url)
    return found


def create(conn: Connection, run_id: int, title: str) -> int:
    return conn.execute(stories.insert().values(run_id=run_id, title=title)).inserted_primary_key[0]


def add_item(conn: Connection, run_id: int, story_id: int, item_id: int, matched_by: str) -> None:
    conn.execute(story_items.insert().values(run_id=run_id, story_id=story_id, item_id=item_id, matched_by=matched_by))


def log_judgement(conn: Connection, run_id: int, item_a: int, item_b: int, similarity: float, why: str, answer: str) -> None:
    conn.execute(
        judge_log.insert().values(
            run_id=run_id, item_a=item_a, item_b=item_b, similarity=similarity, why_uncertain=why, answer=answer
        )
    )


def link_in_thread(conn: Connection, run_id: int, story_a: int, story_b: int) -> None:
    """Put two stories on the same subject in one thread, without merging them or joining two existing threads."""
    found = {row.id: row for row in conn.execute(select(stories).where(stories.c.id.in_([story_a, story_b])))}
    thread_a, thread_b = found[story_a].thread_id, found[story_b].thread_id
    if thread_a and thread_b:
        return
    thread = thread_a or thread_b
    if not thread:
        thread = conn.execute(threads.insert().values(run_id=run_id, title=found[story_a].title)).inserted_primary_key[0]
    conn.execute(stories.update().where(stories.c.id.in_([story_a, story_b])).values(thread_id=thread))


def split_off(conn: Connection, run_id: int, story_id: int, item_ids: list[int], reason: str) -> list[int]:
    """Take these items out of a story they do not belong to, and record it. Returns the items taken out.

    An item taken out is in no story, so the next run groups it again: it may join the story it does belong to, or
    become one of its own. A story is never emptied this way: if these are all its items, nothing is done.
    """
    mine = {row.item_id for row in conn.execute(select(story_items.c.item_id).where(story_items.c.story_id == story_id))}
    going = [item_id for item_id in item_ids if item_id in mine]
    if not going or len(going) >= len(mine):
        return []
    conn.execute(story_items.delete().where((story_items.c.story_id == story_id) & story_items.c.item_id.in_(going)))
    conn.execute(splits.insert(), [{"run_id": run_id, "item_id": item_id, "story_id": story_id, "reason": reason} for item_id in going])
    return going


def kept_apart(conn: Connection, item_ids: list[int]) -> dict[int, set[int]]:
    """{item id: the stories it was once taken out of, and so must not be put back into}."""
    found: dict[int, set[int]] = {}
    for row in conn.execute(select(splits.c.item_id, splits.c.story_id).where(splits.c.item_id.in_(item_ids))):
        found.setdefault(row.item_id, set()).add(row.story_id)
    return found


def members(conn: Connection, story_ids: list[int]) -> list[Row]:
    """Every item of the given stories, with the story's title and why the item is in it."""
    query = (
        select(stories.c.id.label("story_id"), stories.c.title.label("story_title"),
               items.c.source, items.c.title, items.c.url, story_items.c.matched_by)
        .select_from(stories.join(story_items).join(items))
        .where(stories.c.id.in_(story_ids))
        .order_by(stories.c.id, items.c.id)
    )
    return list(conn.execute(query))
