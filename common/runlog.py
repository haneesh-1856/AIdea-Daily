"""The run record: which steps of a day's run are done, so a rerun resumes instead of restarting."""

from datetime import date, datetime, timezone

from sqlalchemy import Connection, Row, select

from common.db import run_steps, runs

STEPS = {
    1: "start",
    2: "fetch",
    3: "clean_store",
    4: "group",
    5: "score",
    6: "select",
    7: "plan",
    8: "write",
    9: "check_fit",
    10: "voice",
    11: "assemble",
    12: "package",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def latest_run(conn: Connection, run_date: date) -> Row | None:
    return conn.execute(
        select(runs).where(runs.c.run_date == run_date).order_by(runs.c.attempt.desc()).limit(1)
    ).first()


def last_before(conn: Connection, run_date: date) -> Row | None:
    """The last run made for an earlier date: the run behind the episode before this one."""
    return conn.execute(select(runs).where(runs.c.run_date < run_date).order_by(runs.c.id.desc()).limit(1)).first()


def create_run(conn: Connection, run_date: date, settings: dict) -> Row:
    previous = latest_run(conn, run_date)
    conn.execute(
        runs.insert().values(
            run_date=run_date,
            attempt=previous.attempt + 1 if previous else 1,
            status="running",
            started_at=_now(),
            settings=settings,
        )
    )
    return latest_run(conn, run_date)


def begin_step(conn: Connection, run_id: int, step: int) -> None:
    where = (run_steps.c.run_id == run_id) & (run_steps.c.step == step)
    values = {"status": "running", "started_at": _now(), "finished_at": None, "detail": None}
    if conn.execute(select(run_steps.c.id).where(where)).first():
        conn.execute(run_steps.update().where(where).values(**values))
    else:
        conn.execute(run_steps.insert().values(run_id=run_id, step=step, name=STEPS[step], **values))


def finish_step(conn: Connection, run_id: int, step: int, status: str = "done", detail: str | None = None) -> None:
    where = (run_steps.c.run_id == run_id) & (run_steps.c.step == step)
    conn.execute(run_steps.update().where(where).values(status=status, finished_at=_now(), detail=detail))


def skip_step(conn: Connection, run_id: int, step: int, detail: str) -> None:
    """Record a step that is not built as passed over, so the steps after it can run."""
    begin_step(conn, run_id, step)
    finish_step(conn, run_id, step, "skipped", detail)


def done_steps(conn: Connection, run_id: int) -> set[int]:
    """The steps that are finished or were passed over."""
    rows = conn.execute(
        select(run_steps.c.step).where((run_steps.c.run_id == run_id) & run_steps.c.status.in_(("done", "skipped")))
    )
    return {row.step for row in rows}


def reopen(conn: Connection, run_id: int, from_step: int) -> None:
    """Forget that the steps from `from_step` on were done, so that they run again on what the earlier steps left."""
    conn.execute(run_steps.delete().where((run_steps.c.run_id == run_id) & (run_steps.c.step >= from_step)))
    conn.execute(runs.update().where(runs.c.id == run_id).values(status="running", finished_at=None))


def steps_of(conn: Connection, run_id: int) -> list[Row]:
    return list(conn.execute(select(run_steps).where(run_steps.c.run_id == run_id).order_by(run_steps.c.step)))


def finish_run(conn: Connection, run_id: int, status: str, cost: float) -> None:
    conn.execute(runs.update().where(runs.c.id == run_id).values(status=status, finished_at=_now(), cost=cost))


def next_step(conn: Connection, run_id: int) -> int | None:
    """The first step not yet done, or None when the whole run is finished."""
    done = done_steps(conn, run_id)
    return next((step for step in STEPS if step not in done), None)
