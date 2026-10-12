"""Database tables and connection. All database access goes through this folder."""

from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Engine,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.engine import make_url

metadata = MetaData()

# One row per attempt at a day's run. A forced rerun adds a new attempt and keeps the old one.
runs = Table(
    "runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_date", Date, nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("status", String(20), nullable=False),  # running, done, failed
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("settings", JSON, nullable=False),  # the settings as they were when the run started
    Column("cost", Float),  # US dollars spent on the model, set when the run finishes
    UniqueConstraint("run_date", "attempt"),
)

run_steps = Table(
    "run_steps",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),
    Column("step", Integer, nullable=False),
    Column("name", String(40), nullable=False),
    Column("status", String(20), nullable=False),  # running, done, failed
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("detail", Text),
    UniqueConstraint("run_id", "step"),
)

# One row per source per run, so a feed that has been dead for days gets noticed.
source_health = Table(
    "source_health",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),
    Column("source", String(80), nullable=False),
    Column("ok", Boolean, nullable=False),
    Column("entries", Integer, nullable=False),
    Column("error", Text),
    UniqueConstraint("run_id", "source"),
)

# One row per article per source. The same article from two sources is kept twice on purpose:
# that is evidence for scoring.
items = Table(
    "items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),  # the run that first stored it
    Column("source", String(80), nullable=False),
    Column("kind", String(20), nullable=False),  # primary, press, newsletter, traction
    Column("title", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("canonical_url", Text, nullable=False, index=True),
    Column("summary", Text),
    Column("published_at", DateTime(timezone=True), index=True),  # empty when the source gave no date
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("points", Integer),
    Column("comments", Integer),
    Column("discussion_url", Text),
    UniqueConstraint("source", "canonical_url"),
)

# The cleaned links found inside an item's description. An item that links to another item's
# article is evidence that both are about the same story.
item_links = Table(
    "item_links",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("item_id", ForeignKey("items.id"), nullable=False, index=True),
    Column("canonical_url", Text, nullable=False),
    UniqueConstraint("item_id", "canonical_url"),
)

# Stories on the same subject, linked without being merged.
threads = Table(
    "threads",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),
    Column("title", Text, nullable=False),
)

# One row per event: who did what, and when.
stories = Table(
    "stories",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),  # the run that first saw it
    Column("title", Text, nullable=False),
    Column("thread_id", ForeignKey("threads.id")),
)

# Which item is in which story, and why it was put there.
story_items = Table(
    "story_items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("story_id", ForeignKey("stories.id"), nullable=False, index=True),
    Column("item_id", ForeignKey("items.id"), nullable=False, unique=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),  # the run that placed it
    Column("matched_by", String(20), nullable=False),  # new, link, mention, similarity, judge
)

# An item taken out of a story because the writer found it reports a different event. The item goes back to be
# grouped again, and this row keeps it from ever being put back into that story.
splits = Table(
    "splits",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),  # the run whose writer found it
    Column("item_id", ForeignKey("items.id"), nullable=False),
    Column("story_id", ForeignKey("stories.id"), nullable=False),  # the story it was taken out of
    Column("reason", Text, nullable=False),
)

# Every pair of items too uncertain to merge by rule, and what the model answered.
judge_log = Table(
    "judge_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),
    Column("item_a", ForeignKey("items.id"), nullable=False),
    Column("item_b", ForeignKey("items.id"), nullable=False),
    Column("similarity", Float, nullable=False),
    Column("why_uncertain", String(40), nullable=False),
    Column("answer", String(20), nullable=False),  # yes, no, not asked, failed
)

# Every request made to the language model, with its size and cost.
model_calls = Table(
    "model_calls",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),
    Column("step", Integer, nullable=False),
    Column("purpose", String(40), nullable=False),
    Column("story_id", ForeignKey("stories.id")),
    Column("model", String(80), nullable=False),
    Column("tokens_in", Integer, nullable=False),
    Column("tokens_out", Integer, nullable=False),
    Column("cost", Float, nullable=False),  # US dollars
)

# One row per story per run, never overwritten.
scores = Table(
    "scores",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),
    Column("story_id", ForeignKey("stories.id"), nullable=False),
    Column("total", Float, nullable=False),
    Column("topic", String(40)),
    Column("signals", JSON, nullable=False),  # what was counted: outlets, primary, hn_points, hn_comments, staying, focus
    Column("points", JSON, nullable=False),  # the same signals after scaling and weighting; they add up to total
    UniqueConstraint("run_id", "story_id"),
)

# The text of an item's full article, kept for a limited time.
articles = Table(
    "articles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("item_id", ForeignKey("items.id"), nullable=False, unique=True),
    Column("status", String(20), nullable=False),  # ok, refused, failed, no text
    Column("text", Text),  # emptied when the retention period is over
    Column("words", Integer, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
)

selections = Table(
    "selections",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),
    Column("story_id", ForeignKey("stories.id"), nullable=False),
    Column("rank", Integer, nullable=False),
    Column("score", Float, nullable=False),
    Column("kind", String(20), nullable=False),  # new, update, correction
    Column("label", String(20), nullable=False),  # confirmed, reported, rumour
    Column("item_ids", JSON, nullable=False),  # the sources to write from, most authoritative first
    Column("first_seen", Date),  # set when the story began on an earlier day and is only now in an episode
    Column("fill", String(20)),  # how it came in when not by the final list: recovered, brief, culture, know, watch
    UniqueConstraint("run_id", "story_id"),
)

episodes = Table(
    "episodes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, unique=True),
    Column("length_minutes", Integer, nullable=False),
    Column("word_cap", Integer, nullable=False),
    Column("words", Integer),  # the fitted script, set by step 9
    Column("audio_seconds", Float),  # the length of the episode file, set by step 11 when there is audio
    Column("status", String(20), nullable=False),  # planned, ready, held
)

episode_stories = Table(
    "episode_stories",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("episode_id", ForeignKey("episodes.id"), nullable=False),
    Column("story_id", ForeignKey("stories.id"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("segment", String(20), nullable=False),  # corrections, main, quick_hits, culture, watching
    Column("words", Integer),  # how many words the story should aim for, set by step 7
    Column("form", String(20)),  # full, brief, dropped; set by step 9
    Column("reason", Text),  # why it was shortened or dropped
    UniqueConstraint("episode_id", "story_id"),
)

summaries = Table(
    "summaries",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False),
    Column("story_id", ForeignKey("stories.id"), nullable=False),
    Column("headline", Text),
    Column("what_happened", Text),
    Column("differences", Text),  # how sources see it
    Column("brief", Text),
    Column("flag", String(20)),  # different_events, nothing_new, failed
    Column("note", Text),  # the model's reason for a flag, or the error
    UniqueConstraint("run_id", "story_id"),
)

# The script, one sentence per row, in speaking order.
script_lines = Table(
    "script_lines",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("position", Integer, nullable=False),
    Column("story_id", ForeignKey("stories.id")),  # empty for the linking parts
    Column("part", String(20), nullable=False),  # opening, headline, cue, title, credits, intro, what, how, brief, watch, closing
    Column("text", Text, nullable=False),
    Column("status", String(20), nullable=False),  # draft, kept, removed, unused
)

# One spoken clip per script line, with its length, so that caption timings are known later.
clips = Table(
    "clips",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("line_id", ForeignKey("script_lines.id"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("file", Text, nullable=False),
    Column("seconds", Float, nullable=False),
    Column("pause_after", Float, nullable=False),  # silence to leave before the next clip
    UniqueConstraint("run_id", "line_id"),
)

check_log = Table(
    "check_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("story_id", ForeignKey("stories.id")),
    Column("text", Text),  # the sentence, when the entry is about one
    Column("reason", Text, nullable=False),
    Column("action", String(30), nullable=False),  # removed, shortened to brief, dropped, held
)

# The longer episodes made beside the regular one, from the same stories: one row per format per run.
format_scripts = Table(
    "format_scripts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("format", String(20), nullable=False),  # podcast, duo
    Column("note", Text),  # why the script or its audio could not be made, when it could not
    Column("shortfall", Text),  # the planner's reason, when the day's news cannot carry the wanted length
    Column("flagged", JSON),  # sentences with a number or name not in the sources, set by step 9
    Column("clips", JSON),  # the spoken pieces, set by step 10 and emptied by step 11: {key: {"file", "seconds"}}
    Column("voice_seconds", Float),  # how long step 10 took to speak it
    Column("audio_seconds", Float),  # the length of the episode file, set by step 11
    UniqueConstraint("run_id", "format"),
)

# A longer episode's segments in speaking order. The plan is stored first; each segment's lines when it is written.
format_segments = Table(
    "format_segments",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("format", String(20), nullable=False),
    Column("position", Integer, nullable=False),
    Column("kind", String(20), nullable=False),  # cold_open, intro, stories, closing
    Column("title", Text, nullable=False),
    Column("angle", Text),  # what the segment is about, from the plan
    Column("story_ids", JSON, nullable=False),  # the stories it tells, in order; empty for the linking segments
    Column("words", Integer, nullable=False),  # how many spoken words it should aim for
    Column("lines", JSON),  # [{"speaker", "text"}], empty until the segment is written
    Column("illustrations", JSON),  # the examples the writer made up itself, so that they can be told from facts
)


def connect(url: str) -> Engine:
    """Open the database and create any tables that do not exist yet."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database:
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


def _add_missing_columns(engine: Engine) -> None:
    """create_all never changes a table that exists, so columns added to the code later are added here."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in present:
                    kind = column.type.compile(engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}'))


def describe(url: str) -> str:
    """Where the database is, without the password."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        return f"local file {parsed.database}"
    return f"PostgreSQL at {parsed.host}"
