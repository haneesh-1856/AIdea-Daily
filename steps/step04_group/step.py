"""Step 4, Group: merge items about the same event into one story, in three layers from certain to uncertain."""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import numpy as np
from sqlalchemy.exc import SQLAlchemyError

from common import articles, db, model, runlog, stories
from common.report import step_folder, write_report
from common.settings import ROOT, database_url

STEP = 4
# A new story takes its title from its most authoritative item.
KIND_ORDER = {"primary": 0, "press": 1, "newsletter": 2, "traction": 3}
Embed = Callable[[list[str]], np.ndarray]  # texts -> one row of numbers per text, capturing its meaning
Read = Callable[[str], tuple[str, str | None]]  # an article's address -> (status, its text)
OPENING_WORDS = 150  # how much of an article the judge is shown

WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+'’-]*[A-Za-z0-9]|[A-Za-z0-9]")
# A number standing alone, such as the 4 in "Large 4" or 5.5: not money, a percentage, a year or a size like 501B.
VERSION = re.compile(r"(?<![\w$.,])(?<!\d-)\d{1,2}(?:\.\d+)*(?![\w%]|[.,-]\d)")
STOPWORDS = frozenset(
    "the a an and or but of to in on for with from by at as is are was were be been it its this that these those "
    "new how why what when who will can may says say said after before over into about more most than not no "
    "you your our their his her they we he she has have had do does did up out now just also all one two "
    # Days and months are capitalised like names and say nothing about which event an item reports.
    "monday tuesday wednesday thursday friday saturday sunday january february march april june july august "
    "september october november december".split()
)
JUDGE_RULES = (
    "You compare two news items and decide whether they report the same event.\n"
    "An event is one thing that happened: who did what, and when.\n"
    "Two items about the same company, product or topic are not the same event unless they report the same "
    "announcement, release, incident or decision.\n"
    "A reaction or commentary piece about an event counts as the same event.\n"
    "An announcement of several things, and an item about one of those things, are the same event.\n"
    "When the opening of an article is given, judge from it and not from the headline alone.\n"
    "A different version number means a different event.\n"
    "Judge from the two items only. If you cannot tell, answer false."
)
JUDGE_ANSWER = {
    "type": "object",
    "properties": {"same_event": {"type": "boolean"}},
    "required": ["same_event"],
    "additionalProperties": False,
}


class GroupError(Exception):
    """The step could not run. The message says why."""


@dataclass
class GroupResult:
    run_id: int
    run_date: date
    state: str  # grouped, already_done
    items: int
    new_stories: int
    joined: int  # items put into a story that existed before this run
    uncertain: int  # pairs too uncertain to merge by rule
    report: Path


@dataclass
class Uncertain:
    similarity: float
    a: object
    b: object
    why: str
    answer: str = "not asked"


@dataclass
class Groups:
    """Items being gathered into stories. Two stories that already exist are never joined:
    a missed merge lowers a score, a wrong merge corrupts a story."""

    rows: list
    parent: dict = field(default_factory=dict)
    story: dict = field(default_factory=dict)  # for a root: the existing story its group belongs to
    reasons: dict = field(default_factory=dict)  # item id -> why it was first joined to another item
    apart: dict = field(default_factory=dict)  # item id -> stories it was taken out of and must not rejoin
    barred: dict = field(default_factory=dict)  # for a root: the stories its group must not join

    def __post_init__(self):
        self.parent = {row.id: row.id for row in self.rows}
        self.story = {row.id: row.story_id for row in self.rows}
        first_of_story: dict[int, int] = {}
        for row in self.rows:
            if row.story_id:
                self.parent[self.find(row.id)] = self.find(first_of_story.setdefault(row.story_id, row.id))
        self.barred = {row.id: set() for row in self.rows}
        for row in self.rows:
            self.barred[self.find(row.id)] |= set(self.apart.get(row.id, ()))

    def find(self, item_id: int) -> int:
        while self.parent[item_id] != item_id:
            self.parent[item_id] = self.parent[self.parent[item_id]]
            item_id = self.parent[item_id]
        return item_id

    def together(self, a: int, b: int) -> bool:
        return self.find(a) == self.find(b)

    def can_join(self, a: int, b: int) -> bool:
        a, b = self.find(a), self.find(b)
        if a == b or (self.story[a] and self.story[b] and self.story[a] != self.story[b]):
            return False
        # An item the writer took out of a story is never put back into it, whatever the rules say.
        return (self.story[a] or self.story[b]) not in (self.barred[a] | self.barred[b])

    def join(self, a: int, b: int, reason: str) -> bool:
        if not self.can_join(a, b):
            return False
        root_a, root_b = self.find(a), self.find(b)
        self.parent[root_b] = root_a
        self.story[root_a] = self.story[root_a] or self.story[root_b]
        self.barred[root_a] |= self.barred[root_b]
        self.reasons.setdefault(a, reason)
        self.reasons.setdefault(b, reason)
        return True

    def new_groups(self) -> list[tuple[int | None, list]]:
        """(existing story id or None, the items not yet in a story that belong together)."""
        found: dict[int, list] = {}
        for row in self.rows:
            if not row.story_id:
                found.setdefault(self.find(row.id), []).append(row)
        return [(self.story[root], members) for root, members in found.items()]


def link_layer(groups: Groups, links: dict[int, set[str]]) -> list:
    """Certain matches: the same link, or one item linking to another's article.

    Returns the digests: items that link to several stories and so are merged with none.
    """
    by_link: dict[str, list] = {}
    for row in groups.rows:
        by_link.setdefault(row.canonical_url, []).append(row)
    for same in by_link.values():
        for row in same[1:]:
            groups.join(same[0].id, row.id, "link")

    # Mentions are all worked out before any is applied, so the result does not depend on item order.
    mentions, digests = [], []
    for row in groups.rows:
        targets: dict[int, int] = {}  # group -> one item in it that this row links to
        for link in links.get(row.id, ()):
            for other in by_link.get(link, ()):
                # A source linking to its own earlier post is giving background, not reporting the same event.
                if other.source != row.source and not groups.together(row.id, other.id):
                    targets.setdefault(groups.find(other.id), other.id)
        if len(targets) == 1:
            mentions.append((row.id, next(iter(targets.values()))))
        elif targets and not row.story_id:
            digests.append(row)
    for item_id, target in mentions:
        groups.join(item_id, target, "mention")
    return digests


def names_of(row) -> set[str]:
    """Words in the item that look like names: capitalised or containing a digit, and not just opening a sentence.

    A name has a letter in it. A bare number is not one: "$1,000" and "129,000" both leave the piece "000", and on
    7 October 2026 that piece alone merged a story about startup credits with one about a security programme.
    """
    found = set()
    for sentence in re.split(r"(?<=[.!?:])\s+", f"{row.title}. {(row.summary or '')[:300]}"):
        for position, word in enumerate(WORD.findall(sentence)):
            if not any(c.isalpha() for c in word):
                continue
            inner = any(c.isupper() or c.isdigit() for c in word[1:])
            if inner or (position > 0 and word[0].isupper()) or word[0].isdigit():
                found.add(word.lower().removesuffix("'s").removesuffix("’s"))
    return found - STOPWORDS


def distinctive_names(rows: list, common_names: list[str]) -> dict[int, set[str]]:
    """Per item, its names that are rare enough to identify a story.

    The same product or company is not enough, so the AI keywords and names that appear in many items are left out.
    """
    names = {row.id: names_of(row) for row in rows}
    seen: dict[str, int] = {}
    for found in names.values():
        for name in found:
            seen[name] = seen.get(name, 0) + 1
    limit = max(10, round(0.08 * len(rows)))
    common = {name.lower() for name in common_names}
    return {
        item_id: {name for name in found if seen[name] <= limit and name not in common and len(name) > 1}
        for item_id, found in names.items()
    }


def versions_of(title: str) -> set[str]:
    return set(VERSION.findall(title))


def meaning_layer(groups: Groups, vectors: np.ndarray, names: dict[int, set[str]], settings: dict) -> list[Uncertain]:
    """Likely matches: items close in meaning are merged when every rule allows it.

    Returns the pairs that were close but not merged, most alike first, for the language model to judge.
    """
    rows = groups.rows
    unit = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    alike = unit @ unit.T
    close = []
    for i, a in enumerate(rows):
        for j in range(i + 1, len(rows)):
            # Two items already in stories have nothing left to decide.
            if alike[i, j] >= settings["judge_from"] and not (a.story_id and rows[j].story_id):
                close.append((float(alike[i, j]), a, rows[j]))
    close.sort(key=lambda pair: -pair[0])

    uncertain = []
    for similarity, a, b in close:
        versions_a, versions_b = versions_of(a.title), versions_of(b.title)
        if similarity < settings["merge_at"]:
            why = "in the middle band"
        elif a.source == b.source:
            why = "same source"  # one outlet publishing twice is usually two different pieces
        elif versions_a and versions_b and not versions_a & versions_b:
            why = "different version numbers"
        elif not names[a.id] & names[b.id]:
            why = "no shared distinctive name"
        else:
            groups.join(a.id, b.id, "similarity")
            continue
        uncertain.append(Uncertain(similarity, a, b, why))
    return [pair for pair in uncertain if groups.can_join(pair.a.id, pair.b.id)]


def read_openings(engine, pairs: list[Uncertain], read: Read) -> tuple[dict[int, str], list]:
    """The opening of the article behind each item of these pairs: {item id: its first words}, and what was read now.

    A headline often does not say what an article announces, and on 8 October 2026 the judge kept a company's own
    post about a launch apart from the press article on it for that reason. An article already stored is not read
    again, and one that was refused is not asked for twice.
    """
    rows = list({row.id: row for pair in pairs for row in (pair.a, pair.b)}.values())
    with engine.connect() as conn:
        stored = {row.id: articles.get(conn, row.id) for row in rows}
    to_read = [row for row in rows if stored[row.id] is None]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda row: read(row.url), to_read))
    texts = {row.id: stored[row.id].text for row in rows if stored[row.id] is not None and stored[row.id].text}
    texts |= {row.id: text for row, (status, text) in zip(to_read, results) if status == "ok" and text}
    openings = {item_id: " ".join(text.split()[:OPENING_WORDS]) for item_id, text in texts.items()}
    return openings, [(row, status, text) for row, (status, text) in zip(to_read, results)]


def judge_layer(groups: Groups, uncertain: list[Uncertain], settings: dict, ask: model.Ask | None,
                openings: dict[int, str] | None = None) -> list[model.Reply]:
    """Uncertain matches: the language model answers one yes-or-no question per pair. It sees the two items, and
    the opening of each article when it could be read."""
    openings = openings or {}
    replies = []
    for pair in uncertain:
        # An earlier answer may have settled this pair already.
        if not groups.can_join(pair.a.id, pair.b.id):
            pair.answer = "settled by an earlier pair"
            continue
        if ask is None or len(replies) >= settings["group"]["max_judge_pairs"]:
            continue
        question = "\n\n".join(
            f"Item {letter} ({row.source}): {row.title}\n{row.summary or '(no description)'}"
            + (f"\nOpening of the article: {openings[row.id]}" if row.id in openings else "")
            for letter, row in (("A", pair.a), ("B", pair.b))
        )
        try:
            reply = ask(settings["model"], JUDGE_RULES, question, JUDGE_ANSWER)
        except model.ModelError:
            pair.answer = "failed"  # unsure, so the two stay apart
            continue
        replies.append(reply)
        pair.answer = "yes" if reply.data.get("same_event") is True else "no"
        if pair.answer == "yes":
            groups.join(pair.a.id, pair.b.id, "judge")
    return replies


def local_embed(model_name: str, root: Path) -> Embed:
    # Imported here because loading it takes seconds, and tests bring their own.
    from fastembed import TextEmbedding

    try:
        embedder = TextEmbedding(model_name, cache_dir=str(root / "data" / "models"))
    except Exception as exc:  # a failed download or an unknown model name
        raise GroupError(f"The local model {model_name} could not be loaded: {exc}") from exc
    return lambda texts: np.array(list(embedder.embed(texts)))


def group(run_date: date, *, root: Path = ROOT, embed: Embed | None = None, ask: model.Ask | None = None,
          read: Read | None = None) -> GroupResult:
    url = database_url(root)
    report = step_folder(root, run_date, STEP) / "report.md"

    try:
        engine = db.connect(url)
        with engine.begin() as conn:
            run = runlog.latest_run(conn, run_date)
            done = runlog.done_steps(conn, run.id) if run else set()
            if STEP - 1 not in done:
                raise GroupError(f"There are no stored items for {run_date}. Run step 3 first.")
            if STEP in done:
                return GroupResult(run.id, run_date, "already_done", 0, 0, 0, 0, report)
            runlog.begin_step(conn, run.id, STEP)

            new = stories.ungrouped_items(conn)
            rows = list(new)
            if new:
                # Stories from the last few days can still gain items; older ones are left alone.
                days = run.settings["collect"]["max_age_days"]
                rows += stories.grouped_items(conn, max(row.fetched_at for row in new) - timedelta(days=days))
            links = stories.links_of(conn, [row.id for row in rows])
            apart = stories.kept_apart(conn, [row.id for row in rows])

        # The settings frozen in the run are used, not the files. No transaction is open while models work.
        settings = {**run.settings, "model": model.chosen(run.settings, root)}
        groups = Groups(rows, apart=apart)
        digests = link_layer(groups, links)
        uncertain, replies, read_now, openings = [], [], [], {}
        if len(rows) > 1:
            embed = embed or local_embed(settings["group"]["embedding_model"], root)
            vectors = embed([f"{row.title}. {(row.summary or '')[:300]}" for row in rows])
            names = distinctive_names(rows, settings["collect"]["ai_keywords"])
            uncertain = meaning_layer(groups, vectors, names, settings["group"])
            if ask is None and model.configured(settings["model"]):
                ask = model.ask
                if read is None:
                    # Imported here: only a real run reads pages, and tests bring their own stand-in.
                    from steps.step06_select.step import Reader
                    read = Reader().read
            if ask and read:
                openings, read_now = read_openings(engine, uncertain[:settings["group"]["max_judge_pairs"]], read)
            replies = judge_layer(groups, uncertain, settings, ask, openings)

        with engine.begin() as conn:
            story_of = {row.id: row.story_id for row in rows}
            touched, created, joined = [], 0, 0
            for story_id, found in groups.new_groups():
                seed = None
                if story_id is None:
                    seed = min(found, key=lambda row: (KIND_ORDER.get(row.kind, 9), row.id))
                    story_id = stories.create(conn, run.id, seed.title)
                    created += 1
                else:
                    joined += len(found)
                for row in found:
                    stories.add_item(conn, run.id, story_id, row.id, "new" if row is seed else groups.reasons[row.id])
                    story_of[row.id] = story_id
                touched.append(story_id)

            for pair in uncertain:
                stories.log_judgement(conn, run.id, pair.a.id, pair.b.id, pair.similarity, pair.why, pair.answer)
                # Close in meaning and sharing a name, but not the same event: the same subject, so the same thread.
                if story_of[pair.a.id] != story_of[pair.b.id] and names[pair.a.id] & names[pair.b.id]:
                    stories.link_in_thread(conn, run.id, story_of[pair.a.id], story_of[pair.b.id])
            for reply in replies:
                model.record(conn, run.id, STEP, "judge", reply)
            # What was read for the judge is kept, so that step 6 does not read the same page again.
            for row, status, text in read_now:
                articles.save(conn, row.id, status, text, datetime.now(timezone.utc))

            summary = (
                f"{len(new)} items, {created} new stories, {joined} items joined an earlier story, "
                f"{len(uncertain)} uncertain pairs"
            )
            back = [row for row in new if row.id in apart]
            lines = _report_lines(run_date, summary, stories.members(conn, touched), digests, uncertain, settings, back, len(openings))
            runlog.finish_step(conn, run.id, STEP, detail=summary)
    except SQLAlchemyError as exc:
        raise GroupError(f"Could not use the database ({db.describe(url)}): {exc}") from exc

    write_report(root, run_date, STEP, lines)
    return GroupResult(run.id, run_date, "grouped", len(new), created, joined, len(uncertain), report)


def _report_lines(run_date: date, summary: str, members: list, digests: list, uncertain: list, settings: dict,
                  back: tuple | list = (), opened: int = 0) -> list[str]:
    by_story: dict[int, list] = {}
    for row in members:
        by_story.setdefault(row.story_id, []).append(row)
    merged = [found for found in by_story.values() if len(found) > 1]
    why = {
        "new": "first item", "link": "same link", "mention": "one links to the other",
        "similarity": "same meaning", "judge": "the model said same event",
    }
    asked = sum(pair.answer in ("yes", "no") for pair in uncertain)
    judge = settings["model"].get("name") or "no model is chosen, so they were kept apart"

    lines = [
        f"# Step 4, Group: {run_date.isoformat()}",
        "",
        f"{summary}.",
        *(["", f"{len(back)} of these items came back to be grouped again: the writer found they did not belong to the story they "
           "were in. They are never put back into that story.", *(f"- {row.source}: {row.title}" for row in back)] if back else []),
        *(["", f"The model judged the uncertain pairs with the opening of the article for {opened} items, not from headlines alone."]
          if opened else []),
        "",
        f"## Stories with more than one item ({len(merged)})",
        "",
    ]
    for found in merged:
        lines += [f"**{found[0].story_title}**", ""]
        lines += [f"- {row.source}: [{row.title}]({row.url}) ({why[row.matched_by]})" for row in found]
        lines.append("")
    lines += [
        f"## Uncertain pairs ({len(uncertain)})",
        "",
        f"Close in meaning, but a rule stopped an automatic merge. {asked} were put to the model ({judge}). "
        "Marking these by hand, same event or not, is how the thresholds get tuned.",
        "",
        "| Alike | Why uncertain | Answer | Item A | Item B |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {pair.similarity:.2f} | {pair.why} | {pair.answer} | {pair.a.source}: {_cell(pair.a.title)} "
        f"| {pair.b.source}: {_cell(pair.b.title)} |"
        for pair in uncertain
    ]
    lines.append("")
    if digests:
        lines += [
            f"## Left alone: items that link to several stories ({len(digests)})",
            "",
            *(f"- {row.source}: {row.title}" for row in digests),
            "",
        ]
    lines += [f"## Stories with one item ({len(by_story) - len(merged)})", ""]
    lines += [f"- {found[0].source}: {found[0].title}" for found in by_story.values() if len(found) == 1]
    return lines


def _cell(text: str) -> str:
    return text.replace("|", "/")
