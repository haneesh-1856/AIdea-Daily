"""Episodes: the outline of a run's episode, and what became of each story in it."""

from sqlalchemy import Connection, Row, select

from common.db import episode_stories, episodes, selections, stories

# The reason stored for a story left out only because the episode was full. Such a story still appears in the
# newsletter and the show notes.
NO_ROOM = "no room left under the word cap"

LINKING_WORDS = 80  # about what the opening, watch list and closing take
STORY_OVERHEAD_WORDS = 35  # about what one story's headline and narrator's line take
MIN_STORY_WORDS = 100


TIERS = ("quick", "short", "medium", "long")


def tier_words(score: float, lengths: dict, up: int = 0) -> int:
    """The words a story of this score gets under [lengths]. `up` moves it that many tiers longer, for a short day."""
    tier = next((place for place in (3, 2, 1) if score >= lengths[f"{TIERS[place]}_from"]), 0)
    return lengths[f"{TIERS[min(tier + up, 3)]}_words"]


def planned_minutes(stories: list[tuple[float, str | None]], settings: dict) -> float:
    """About how long an episode of these stories runs at their usual lengths. Each story is (score, fill)."""
    lengths = settings["lengths"]
    def words_of(score: float, fill: str | None) -> int:
        if fill in ("watch", "brief"):
            return lengths["quick_words"]
        if fill == "culture":
            return lengths["short_words"]
        return max(tier_words(score, lengths), lengths["short_words"]) if fill == "recovered" else tier_words(score, lengths)

    words = sum(words_of(score, fill) + STORY_OVERHEAD_WORDS for score, fill in stories)
    return (words + LINKING_WORDS) / settings["episode"]["words_per_minute"]


def short_day(stories: list[tuple[float, str | None]], settings: dict) -> bool:
    """Whether the editor's lineup, before anything was added to fill the day, makes an episode under
    `short_day_minutes`. The lineup is all three of the editor's passes; what the short-day rule itself added is not counted."""
    limit = settings["select"].get("short_day_minutes", 0)
    own = [story for story in stories if story[1] not in ("know", "watch")]
    return bool(limit and settings.get("lengths")) and planned_minutes(own, settings) < limit


def story_room(entry, settings: dict, word_cap: int, stories: int) -> tuple[int, int]:
    """How many words one story of the lineup should aim for, and the most it may have.

    Length follows the score: the settings under [lengths] give the words for a long, a medium and a short story,
    and for a quick hit. A story placed among the quick hits is one whatever it scored, and a correction is never
    shorter than a short story. When step 7 fixed the story's length in the plan, that is used.
    """
    limit = settings["write"]["max_story_words"]  # the most any story may ever have
    lengths = settings.get("lengths")
    if getattr(entry, "words", None):
        target = entry.words
    elif not lengths:
        # A run started before length followed the score: the day's stories share the cap equally.
        room = (word_cap - LINKING_WORDS) // max(stories, 1) - STORY_OVERHEAD_WORDS
        target = max(MIN_STORY_WORDS, room // 10 * 10)
    else:
        by_score = next((lengths[f"{tier}_words"] for tier in ("long", "medium", "short") if entry.score >= lengths[f"{tier}_from"]),
                        lengths["quick_words"])
        if entry.segment == "quick_hits":
            target = lengths["quick_words"]
        elif entry.segment == "corrections":
            target = max(by_score, lengths["short_words"])
        else:
            target = by_score
    target = min(limit, target)
    return target, min(limit, int(target * 1.3))


def create(conn: Connection, run_id: int, length_minutes: int, word_cap: int) -> int:
    return conn.execute(
        episodes.insert().values(run_id=run_id, length_minutes=length_minutes, word_cap=word_cap, status="planned")
    ).inserted_primary_key[0]


def add_story(conn: Connection, episode_id: int, story_id: int, position: int, segment: str, words: int | None = None) -> None:
    conn.execute(episode_stories.insert().values(episode_id=episode_id, story_id=story_id, position=position, segment=segment, words=words))


def get(conn: Connection, run_id: int) -> Row | None:
    return conn.execute(select(episodes).where(episodes.c.run_id == run_id)).first()


def lineup(conn: Connection, run_id: int) -> list[Row]:
    """The run's stories in speaking order, each with its selection (rank, score, kind, label, sources) and title."""
    query = (
        select(
            episode_stories.c.story_id, episode_stories.c.position, episode_stories.c.segment,
            episode_stories.c.form, episode_stories.c.reason, episode_stories.c.words,
            selections.c.rank, selections.c.score, selections.c.kind, selections.c.label, selections.c.item_ids,
            selections.c.first_seen, selections.c.fill,
            stories.c.title, stories.c.thread_id,
        )
        .select_from(
            episode_stories.join(episodes)
            .join(stories, stories.c.id == episode_stories.c.story_id)
            .join(selections, (selections.c.story_id == episode_stories.c.story_id) & (selections.c.run_id == episodes.c.run_id))
        )
        .where(episodes.c.run_id == run_id)
        .order_by(episode_stories.c.position)
    )
    return list(conn.execute(query))


def set_form(conn: Connection, episode_id: int, story_id: int, form: str, reason: str | None) -> None:
    where = (episode_stories.c.episode_id == episode_id) & (episode_stories.c.story_id == story_id)
    conn.execute(episode_stories.update().where(where).values(form=form, reason=reason))


def set_audio(conn: Connection, episode_id: int, seconds: float) -> None:
    conn.execute(episodes.update().where(episodes.c.id == episode_id).values(audio_seconds=seconds))


def finish(conn: Connection, episode_id: int, words: int, status: str) -> None:
    conn.execute(episodes.update().where(episodes.c.id == episode_id).values(words=words, status=status))
