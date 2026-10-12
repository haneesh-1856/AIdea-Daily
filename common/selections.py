"""Selections: the stories chosen for a run's episode, and what was covered before."""

from datetime import date, timedelta

from sqlalchemy import Connection, Row, select

from common.db import articles, episode_stories, episodes, items, runs, selections, stories, summaries


def _told():
    """Selections joined to what became of each story, and the test for "it was told".

    Being selected is not being told: the writer may set a story aside, and the check or the cap may drop it. Such a
    story was never heard, so it is not "covered" and must not be held back later as a repeat. A selection whose run
    never reached the check has no outcome yet and still counts, as it always did.
    """
    joined = (
        selections.join(runs)
        .join(stories, stories.c.id == selections.c.story_id)
        .outerjoin(episodes, episodes.c.run_id == runs.c.id)
        .outerjoin(episode_stories, (episode_stories.c.episode_id == episodes.c.id) & (episode_stories.c.story_id == selections.c.story_id))
    )
    return joined, episode_stories.c.form.is_(None) | episode_stories.c.form.in_(("full", "brief"))


def covered_before(conn: Connection, run_date: date) -> tuple[set[int], set[int]]:
    """The stories, and the threads, that an episode before this date already told."""
    joined, told = _told()
    query = select(selections.c.story_id, stories.c.thread_id).select_from(joined).where(runs.c.run_date < run_date, told)
    rows = conn.execute(query).all()
    return {row.story_id for row in rows}, {row.thread_id for row in rows if row.thread_id}


def recent_titles(conn: Connection, run_date: date, days: int = 3) -> list[str]:
    """The titles of the stories told in the episodes of the `days` days before this date, newest first."""
    joined, told = _told()
    query = (
        select(stories.c.title, runs.c.run_date)
        .select_from(joined)
        .where(runs.c.run_date < run_date, runs.c.run_date >= run_date - timedelta(days=days), told)
        .order_by(runs.c.run_date.desc(), selections.c.rank)
    )
    return list(dict.fromkeys(row.title for row in conn.execute(query)))


def save(
    conn: Connection, run_id: int, story_id: int, rank: int, score: float, kind: str, label: str, item_ids: list[int],
    first_seen: date | None = None, fill: str | None = None,
) -> None:
    conn.execute(
        selections.insert().values(
            run_id=run_id, story_id=story_id, rank=rank, score=score, kind=kind, label=label, item_ids=item_ids,
            first_seen=first_seen, fill=fill,
        )
    )


def keep_sources(conn: Connection, run_id: int, story_id: int, item_ids: list[int]) -> None:
    """Narrow a chosen story's sources to these. The writer found that the others report a different event, so they
    are not checked against, linked to or credited for this story."""
    where = (selections.c.run_id == run_id) & (selections.c.story_id == story_id)
    conn.execute(selections.update().where(where).values(item_ids=item_ids))


def chosen(conn: Connection, run_id: int) -> list[Row]:
    """This run's selections in rank order, with each story's title and thread."""
    query = (
        select(selections, stories.c.title, stories.c.thread_id)
        .select_from(selections.join(stories))
        .where(selections.c.run_id == run_id)
        .order_by(selections.c.rank)
    )
    return list(conn.execute(query))


def sources(conn: Connection, item_ids: list[int]) -> list[Row]:
    """The given items in the given order, each with its article's status and text if one was read."""
    query = (
        select(items, articles.c.status.label("article_status"), articles.c.text.label("article_text"),
               articles.c.words.label("article_words"))
        .select_from(items.outerjoin(articles))
        .where(items.c.id.in_(item_ids))
    )
    found = {row.id: row for row in conn.execute(query)}
    return [found[item_id] for item_id in item_ids]


def earlier_reports(conn: Connection, story_id: int, thread_id: int | None, run_date: date) -> list[Row]:
    """What earlier episodes said about this story or its thread, oldest first."""
    same = stories.c.id == story_id
    if thread_id:
        same |= stories.c.thread_id == thread_id
    query = (
        select(runs.c.run_date, stories.c.title, summaries.c.what_happened, summaries.c.brief)
        .select_from(summaries.join(runs).join(stories, stories.c.id == summaries.c.story_id))
        .where(same, runs.c.run_date < run_date, summaries.c.what_happened.is_not(None))
        .order_by(runs.c.run_date, summaries.c.id)
    )
    return list(conn.execute(query))
