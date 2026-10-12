"""Spoken clips: one per script line, with its length and the pause that follows it."""

from sqlalchemy import Connection, Row, select

from common.db import clips


def of_run(conn: Connection, run_id: int) -> list[Row]:
    return list(conn.execute(select(clips).where(clips.c.run_id == run_id).order_by(clips.c.position)))


def forget(conn: Connection, run_id: int) -> None:
    """Remove the run's clips. They were spoken from a script that is about to change."""
    conn.execute(clips.delete().where(clips.c.run_id == run_id))


def save(conn: Connection, run_id: int, line_id: int, position: int, file: str, seconds: float, pause_after: float) -> None:
    conn.execute(clips.delete().where((clips.c.run_id == run_id) & (clips.c.line_id == line_id)))
    conn.execute(
        clips.insert().values(run_id=run_id, line_id=line_id, position=position, file=file, seconds=seconds, pause_after=pause_after)
    )
