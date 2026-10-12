"""Source health: whether each source worked on each run."""

from sqlalchemy import Connection, select

from common.db import source_health


def record(conn: Connection, run_id: int, rows: list[dict]) -> None:
    """Store one row per source for this run, replacing rows from an earlier try of the same run."""
    conn.execute(source_health.delete().where(source_health.c.run_id == run_id))
    conn.execute(source_health.insert(), [{"run_id": run_id, **row} for row in rows])


def failed_sources(conn: Connection, run_id: int) -> list:
    """The sources that did not answer in this run, with the error each gave."""
    query = select(source_health).where((source_health.c.run_id == run_id) & (source_health.c.ok.is_(False)))
    return list(conn.execute(query.order_by(source_health.c.source)))


def failing_streak(conn: Connection, source: str) -> int:
    """How many of the most recent runs in a row this source has failed."""
    rows = conn.execute(
        select(source_health.c.ok).where(source_health.c.source == source).order_by(source_health.c.run_id.desc())
    )
    streak = 0
    for row in rows:
        if row.ok:
            break
        streak += 1
    return streak
