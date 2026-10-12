"""Scores: one row per story per run, with the evidence behind it. Rows are never changed."""

from datetime import date, timedelta

from sqlalchemy import Connection, Row, func, select

from common.db import items, runs, scores, stories, story_items


def active_stories(conn: Connection, run_date: date) -> list[int]:
    """The stories that gained at least one item on this date, in any attempt at its run.

    A forced second attempt finds the day's items already stored, and must still see the day's stories.
    """
    query = (
        select(story_items.c.story_id)
        .select_from(story_items.join(runs, runs.c.id == story_items.c.run_id))
        .where(runs.c.run_date == run_date)
        .distinct()
    )
    return list(conn.execute(query.order_by(story_items.c.story_id)).scalars())


def items_of(conn: Connection, story_ids: list[int]) -> dict[int, list[Row]]:
    """Every item of the given stories, each with the date of the run that placed it and that run's id."""
    query = (
        select(
            story_items.c.story_id, stories.c.title.label("story_title"), stories.c.thread_id,
            items, runs.c.run_date.label("placed_on"), story_items.c.run_id.label("placed_by"),
        )
        .select_from(story_items.join(stories).join(items).join(runs, runs.c.id == story_items.c.run_id))
        .where(story_items.c.story_id.in_(story_ids))
        .order_by(story_items.c.story_id, items.c.id)
    )
    found: dict[int, list[Row]] = {}
    for row in conn.execute(query):
        found.setdefault(row.story_id, []).append(row)
    return found


def save(conn: Connection, run_id: int, story_id: int, total: float, topic: str | None, signals: dict, points: dict) -> None:
    conn.execute(
        scores.insert().values(run_id=run_id, story_id=story_id, total=total, topic=topic, signals=signals, points=points)
    )


def ranked(conn: Connection, run_id: int) -> list[Row]:
    """This run's scores, highest first, with each story's title and thread."""
    query = (
        select(scores, stories.c.title, stories.c.thread_id)
        .select_from(scores.join(stories))
        .where(scores.c.run_id == run_id)
        .order_by(scores.c.total.desc(), scores.c.story_id)
    )
    return list(conn.execute(query))


def topic_counts(conn: Connection, until: date, days: int = 7) -> list[tuple[str, int]]:
    """How many different stories carried each topic over the days up to and including `until`, most first."""
    query = (
        select(scores.c.topic, func.count(scores.c.story_id.distinct()))
        .select_from(scores.join(runs))
        .where(scores.c.topic.is_not(None), runs.c.run_date > until - timedelta(days=days), runs.c.run_date <= until)
        .group_by(scores.c.topic)
    )
    return sorted(((row[0], row[1]) for row in conn.execute(query)), key=lambda pair: (-pair[1], pair[0]))
