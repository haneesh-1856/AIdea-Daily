"""Helpers for the step tests: a project folder in a temporary place, stories without running steps 2 to 4,
a pretend internet for article pages, and a pretend language model."""

import re
import shutil
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select

from common import db, items, model, runlog, stories
from common.settings import ROOT, database_url
from steps.step01_start.step import start

DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


BASELINE = {
    "length_minutes": "15", "words_per_minute": "150", "headlines": "20", "max_stories": "8", "min_score": "4.0",
    "short_day_minutes": "0", "traction_max": "0.0", "culture_max": "0",
    "long_from": "0.0", "medium_from": "0.0", "short_from": "0.0",
    "long_words": "600", "medium_words": "600", "short_words": "600", "quick_words": "600",
}


def make_root(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for name in ("sources.toml", "settings.toml"):
        shutil.copy(ROOT / name, tmp_path / name)
    # Whatever model the real settings name, a test starts with none and brings its own stand-in.
    path = tmp_path / "settings.toml"
    text = re.sub(r'^(provider|name|effort) = "[^"]*"', r'\1 = ""', path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    # The tests keep their own numbers whatever the real settings say: a 15-minute cap at 150 words a minute, the
    # top 8 stories scoring 4 or more, a headline for each, and one length of 600 words for every story. A test of
    # the lengths sets its own. A short day is left short, so that a test of selection sees only what it selected,
    # and Hacker News points add nothing, so that a test's scores are the ratings it gave.
    for key, value in BASELINE.items():
        text, found = re.subn(rf"^{key} = [\d.]+", f"{key} = {value}", text, flags=re.MULTILINE)
        assert found == 1, key
    # The voice step is switched off too; a test that wants it switches it on and brings a stand-in voice.
    text = text.replace("enabled = true", "enabled = false", 1)
    # So are the longer episodes; a test of them switches them on.
    for key in ("podcast", "duo"):
        text, found = re.subn(rf"^{key} = true", f"{key} = false", text, flags=re.MULTILINE)
        assert found == 1, key
    path.write_text(text, encoding="utf-8")
    return tmp_path


def edit_settings(root, old, new):
    path = root / "settings.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def item(source, kind="press", title="Lab ships a thing", **extra):
    """An item whose feed description repeats its title, unless a summary is given."""
    return {"source": source, "kind": kind, "title": title, "summary": f"{title}.", **extra}


def link_of(source, name, day=DAY, number=0):
    return f"https://{source.replace(' ', '').lower()}.example/{name}/{day}/{number}"


def grouped(root, found, day=DAY, into=None, threads=None):
    """Stands in for steps 1 to 4: opens the day's run and stores each list of items as one story.

    found maps a story name to its items; `into` maps a story name to an existing story id to add to;
    `threads` lists pairs of story names to link in a thread. Returns {story name: story id}.
    """
    started = start(day, root=root, checks=[])
    ids = dict(into or {})
    with db.connect(database_url(root)).begin() as conn:
        for name, members in found.items():
            if name not in ids:
                ids[name] = stories.create(conn, started.run_id, name)
            for number, one in enumerate(members):
                link = link_of(one["source"], name, day, number)
                items.upsert(conn, started.run_id, {"url": link, "canonical_url": link, "fetched_at": NOW, **one})
                item_id = conn.execute(select(db.items.c.id).where(db.items.c.canonical_url == link)).scalar()
                stories.add_item(conn, started.run_id, ids[name], item_id, "new")
        for first, second in threads or ():
            stories.link_in_thread(conn, started.run_id, ids[first], ids[second])
        for step in (2, 3, 4):
            runlog.begin_step(conn, started.run_id, step)
            runlog.finish_step(conn, started.run_id, step)
    return ids


def rows(root, table, **where):
    with db.connect(database_url(root)).connect() as conn:
        query = select(table)
        for column, value in where.items():
            query = query.where(table.c[column] == value)
        return conn.execute(query.order_by(table.c.id)).all()


def article(*paragraphs):
    """A web page with menus and an advert around the given paragraphs."""
    body = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    return (
        "<html><head><title>Page</title></head><body><nav><a href='/'>Home</a> <a href='/about'>About us</a></nav>"
        f"<article><h1>Headline</h1>{body}</article>"
        "<aside>Advert: buy one get one free today only</aside><footer>Copyright and cookie settings</footer></body></html>"
    )


FILLER = (
    "The announcement was made at an event for customers and partners, and the company published the details "
    "on its website afterwards. People who follow the field closely said they would read the full material "
    "before drawing conclusions, and several of them pointed out that independent tests usually take a few weeks "
    "to appear. The company said it would publish more information over the coming months as the work continues. "
    "Nobody at the event wanted to guess what the wider effect might be, and most of the questions afterwards "
    "were about when the material would be available and who would be able to use it."
)
MORE = (
    "Reaction over the following days was mixed. Some customers welcomed the change and said it solved a problem "
    "they had raised many times, while others asked whether the price would stay the same after the first year. "
    "A spokesperson declined to answer that question directly and pointed to the published terms instead. "
    "Industry groups asked for a meeting to discuss how the change affects smaller firms, and a date for that "
    "meeting is expected to be set before the end of the season, according to people familiar with the planning."
)


def fake_web(monkeypatch, pages=None):
    """Replaces step 6's requests. pages maps an address to page text, a status code, or an exception to raise.
    An address not listed answers 404. Returns the list of addresses asked for."""
    from steps.step06_select import step as select_step

    pages = pages or {}
    asked = []

    def get(url):
        asked.append(url)
        answer = pages.get(url, 404)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, int):
            return httpx.Response(answer, text="")
        return httpx.Response(200, text=answer)

    monkeypatch.setattr(select_step, "get", get)
    return asked


STORY = {
    "different_events": False, "nothing_new": False, "note": "",
    "headline": "Lab ships a thing.",
    "what_happened": "Lab shipped a thing. It is available now.",
    "how_sources_see_it": "Coverage broadly agrees.",
    "brief": "Lab shipped a thing.",
}
LINKING = {"opening": "Good morning. Here is the AI news.", "watch_list": "", "closing": "That is all for today."}


QUESTIONS = (
    "immediate_value", "ai_impact", "audience_relevance", "magnitude", "practical_impact", "novelty", "credibility",
    "future_significance",
)


def ratings_for(material, ratings=None, default=7, picks=None, recover=None, lighter=None):
    """Answers a step 5 request as the editor would.

    A rating request: every story gets `default` on all eight questions and "know today", unless its title is in
    `ratings`. A value there is a number, or a dict of the answer's fields. A story titled "weak" gets 1.
    The request for the final list: every candidate is selected, in the order given, which is best score first.
    `picks` selects those titles instead, in that order, and the rest are returned as not selected.
    """
    listed = re.findall(r"^(\d+)\. (.*)$", material, flags=re.MULTILINE)
    # The recovery pass: every story is excluded for "no room", unless `recover` gives its title a decision
    # ("full", "brief", or ("merge", the title of a selected story)).
    if material.startswith("Recovery pass"):
        selected = {title: int(number) for number, title in re.findall(r"^S(\d+)\. (.*?): ", material, flags=re.MULTILINE)}
        decisions = []
        for number, title in listed:
            wanted_as = (recover or {}).get(title, "exclude")
            into = selected[wanted_as[1]] if isinstance(wanted_as, tuple) else 0
            decision = wanted_as[0] if isinstance(wanted_as, tuple) else wanted_as
            decisions.append({"story": int(number), "title": title, "decision": decision, "merge_into": into,
                              "reason": "no room" if decision == "exclude" else f"worth {decision}"})
        return {"decisions": decisions}
    # The lighter-side pass: none is chosen, unless `lighter` lists titles.
    if material.startswith("Lighter side pass"):
        numbers = {title: int(number) for number, title in listed}
        return {"chosen": [{"story": numbers[title], "title": title, "interest": 8 - place, "reason": "people will talk about it"}
                           for place, title in enumerate(lighter or []) if title in numbers]}
    if material.startswith("Scored candidates"):
        numbers = {title: int(number) for number, title in listed}
        chosen = [title for title in picks if title in numbers] if picks is not None else list(numbers)
        return {
            "selected": [
                {"rank": rank, "story": numbers[title], "title": title, "headline": f"{title}, in short", "category": "Other",
                 "action": "KNOW TODAY", "what_happened": f"{title} happened.", "why_it_matters": "It matters.",
                 "what_to_do": "Nothing yet.", "score": 7.0, "why_this_rank": f"placed {rank}"}
                for rank, title in enumerate(chosen, 1)
            ],
            "not_selected": [{"story": number, "title": title, "why_excluded": "no room"} for title, number in numbers.items() if title not in chosen],
        }
    wanted = {"weak": 1, **(ratings or {})}
    answers = []
    for number, title in listed:
        value = wanted.get(title, default)
        fields = value if isinstance(value, dict) else {}
        level = fields.get("level", default) if isinstance(value, dict) else value
        answers.append({
            "story": int(number), "headline": title, **{name: level for name in QUESTIONS},
            "action": "KNOW TODAY", "category": "Other", "new_today": True,
            "stale": False, "reason": f"rated {level}", **{k: v for k, v in fields.items() if k != "level"},
        })
    return {"ratings": answers}


def rater(ratings=None, default=7, picks=None, recover=None, lighter=None):
    """A FakeModel for step 5 alone."""
    return FakeModel(lambda material: ratings_for(material, ratings, default, picks, recover, lighter))


def writer(stories=None, linking=None, ratings=None):
    """A FakeModel for the whole run. It answers a story request by the story's title (default STORY), the linking
    request with `linking` (default LINKING), a rating request as `ratings_for` does, and a grouping question
    with "not the same event". A value may be an exception, which is raised."""
    def answer(material):
        if material.startswith(("Stories to rate", "Scored candidates", "Recovery pass", "Lighter side pass")):
            return ratings_for(material, ratings)
        if material.startswith("Item A"):
            return {"same_event": False}
        if material.startswith("Date:"):
            return linking or LINKING
        return (stories or {}).get(material.splitlines()[0].removeprefix("Story: "), STORY)

    return FakeModel(answer)


class FakeModel:
    """Stands in for the language model. `answer` is called with the material and returns the data to reply with."""

    def __init__(self, answer):
        self.answer = answer
        self.requests = []  # (instructions, material) for every request

    def __call__(self, settings, system, user, schema) -> model.Reply:
        self.requests.append((system, user))
        data = self.answer(user)
        if isinstance(data, Exception):
            raise data
        return model.Reply(data, "test-model", 1000, 100, 0.002)
