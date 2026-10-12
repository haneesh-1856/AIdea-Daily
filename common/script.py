"""The written material of a run: each story's summary, the script one sentence per row, and the check log."""

from sqlalchemy import Connection, Row, select

from common.db import check_log, script_lines, stories, summaries


def save_summary(conn: Connection, run_id: int, story_id: int, **values) -> None:
    conn.execute(summaries.insert().values(run_id=run_id, story_id=story_id, **values))


def summaries_of(conn: Connection, run_id: int) -> dict[int, Row]:
    return {row.story_id: row for row in conn.execute(select(summaries).where(summaries.c.run_id == run_id))}


def forget_failed(conn: Connection, run_id: int) -> None:
    """Remove the summaries of stories the model failed on, so a rerun tries them again."""
    conn.execute(summaries.delete().where((summaries.c.run_id == run_id) & (summaries.c.flag == "failed")))


def replace_lines(conn: Connection, run_id: int, lines: list[dict]) -> None:
    """Store the run's script, numbering the lines in the order given. An earlier draft for the run is replaced."""
    conn.execute(script_lines.delete().where(script_lines.c.run_id == run_id))
    if lines:
        conn.execute(
            script_lines.insert(),
            [{"run_id": run_id, "position": number, "status": "draft", "story_id": None, **line} for number, line in enumerate(lines, 1)],
        )


def set_cues(conn: Connection, run_id: int, cues: dict[int, str]) -> None:
    """Put a spoken cue before the title of each story given ({story id: the cue}), and number the lines again.

    Any cues the run already had are removed first, so calling this with nothing takes them all out.
    """
    conn.execute(script_lines.delete().where((script_lines.c.run_id == run_id) & (script_lines.c.part == "cue")))
    position = 0
    for line in lines_of(conn, run_id):
        if line.part == "title" and line.story_id in cues:
            position += 1
            conn.execute(script_lines.insert().values(
                run_id=run_id, position=position, story_id=line.story_id, part="cue", text=cues[line.story_id], status="kept",
            ))
        position += 1
        if line.position != position:
            conn.execute(script_lines.update().where(script_lines.c.id == line.id).values(position=position))


def set_credits(conn: Connection, run_id: int, sentences: list[str]) -> None:
    """Put these sentences at the very end of the script, after the closing. Any the run already had are removed
    first, so calling this with nothing takes them out."""
    conn.execute(script_lines.delete().where((script_lines.c.run_id == run_id) & (script_lines.c.part == "credits")))
    last = max((line.position for line in lines_of(conn, run_id)), default=0)
    if sentences:
        conn.execute(
            script_lines.insert(),
            [{"run_id": run_id, "position": last + number, "story_id": None, "part": "credits", "text": text, "status": "kept"}
             for number, text in enumerate(sentences, 1)],
        )


def lines_of(conn: Connection, run_id: int) -> list[Row]:
    return list(conn.execute(select(script_lines).where(script_lines.c.run_id == run_id).order_by(script_lines.c.position)))


def set_status(conn: Connection, line_ids: list[int], status: str) -> None:
    if line_ids:
        conn.execute(script_lines.update().where(script_lines.c.id.in_(line_ids)).values(status=status))


def log(conn: Connection, run_id: int, story_id: int | None, text: str | None, reason: str, action: str) -> None:
    conn.execute(check_log.insert().values(run_id=run_id, story_id=story_id, text=text, reason=reason, action=action))


def clear_log(conn: Connection, run_id: int) -> None:
    conn.execute(check_log.delete().where(check_log.c.run_id == run_id))


def log_of(conn: Connection, run_id: int) -> list[Row]:
    """The run's check log in the order written, each entry with its story's title when it has one."""
    query = (
        select(check_log, stories.c.title)
        .select_from(check_log.outerjoin(stories))
        .where(check_log.c.run_id == run_id)
        .order_by(check_log.c.id)
    )
    return list(conn.execute(query))
