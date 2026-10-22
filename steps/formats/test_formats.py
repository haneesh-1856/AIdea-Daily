"""The longer episodes, through steps 8 to 12, with a pretend model and a pretend voice."""

import re

import numpy
import pytest
import soundfile

from common import db, formats, model
from common.facts import Pool
from steps.formats.check import unverified
from steps.formats.voice import gap_after
from steps.formats.write import tidy_plan
from steps.step05_score.step import score
from steps.step06_select.step import select
from steps.step07_plan.step import plan
from steps.step08_write.step import write
from steps import runner
from steps.step09_check_fit.step import check_fit
from steps.step10_voice.step import voice
from steps.step11_assemble.step import assemble
from steps.step12_package.step import package
from steps.testkit import DAY, NOW, edit_settings, fake_web, grouped, item, make_root, rater, rows, writer

RATE = 8000
NEWS = {
    "launch": [item("Lab", "primary", title="Lab ships Orion 4", summary="Orion 4 has 12 billion parameters and costs $20 a month.")],
    "ruling": [item("Press A", title="Lab ships a thing")],
}
SAID = {
    "PRESENTER": "Lab shipped a thing. Imagine you run a shop and it is available now.",
    "HOST": "[surprised] So what happened?!",
    "GUEST": "Lab shipped a thing. It is available now.",
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    fake_web(monkeypatch)
    made = make_root(tmp_path, monkeypatch)
    for key in ("podcast", "duo"):
        edit_settings(made, f"{key} = false", f"{key} = true")
    edit_settings(made, "enabled = false", "enabled = true")
    # Both are spoken, whichever the real settings speak.
    speak = re.search(r"^speak = .*$", (made / "settings.toml").read_text(encoding="utf-8"), flags=re.MULTILINE).group()
    edit_settings(made, speak, 'speak = ["podcast", "duo"]')
    (made / "voice").mkdir()
    for name in ("reference.wav", "reference-voice2-clean.wav"):
        soundfile.write(made / "voice" / name, numpy.zeros(RATE, dtype="float32"), RATE)
    return made


class Talker:
    """Stands in for the model on the whole run. The plan puts every story into one segment, and every line of a
    segment is taken from SAID, unless `plan` or `said` give something else. A value may be an exception, which is
    raised; `said` maps (format, segment title) to the lines to answer with."""

    def __init__(self, plan=None, said=None):
        self.plan, self.said, self.base = plan, said or {}, writer()
        self.requests = []  # (what was asked for, the material)

    def __call__(self, settings, system, user, schema):
        if user.startswith("Episode date:"):
            self.requests.append(("plan", user))
            numbers = [int(number) for number in re.findall(r"^(\d+)\. ", user, flags=re.MULTILINE)]
            data = self.plan if self.plan is not None else {"shortfall": "", "segments": [
                {"kind": "cold_open", "title": "Cold open", "angle": "", "stories": [], "words": 180},
                {"kind": "intro", "title": "Introduction", "angle": "", "stories": [], "words": 160},
                {"kind": "stories", "title": "The biggest stories", "angle": "Two launches.", "stories": numbers, "words": 600},
                {"kind": "closing", "title": "Closing takeaway", "angle": "", "stories": [], "words": 220},
            ]}
        elif user.startswith("Show:"):
            speakers = schema["properties"]["lines"]["items"]["properties"]["speaker"]["enum"]
            name = "duo" if len(speakers) > 1 else "podcast"
            title = re.search(r"^Your segment: \d+\. (.*)$", user, flags=re.MULTILINE).group(1)
            self.requests.append((f"{name}: {title}", user))
            data = self.said.get((name, title), {"lines": [{"speaker": speaker, "text": SAID[speaker]} for speaker in speakers],
                                                 "illustrations": ["the shop"]})
        else:
            return self.base(settings, system, user, schema)
        if isinstance(data, Exception):
            raise data
        return model.Reply(data, "test-model", 1000, 100, 0.002)

    def asked(self, what):
        return [name for name, _ in self.requests if name.startswith(what)]


class Voice:
    """Stands in for the voice model: every piece becomes a tone lasting a third of a second per word."""

    def __init__(self):
        self.calls = []

    def __call__(self, sentences, settings, folder):
        self.calls.append(sentences)
        folder.mkdir(parents=True, exist_ok=True)
        clips = {}
        for one in sentences:
            seconds = max(1, len(one["text"].split())) / 3
            file = folder / f"{one['position']:04d}.wav"
            soundfile.write(file, numpy.full(int(RATE * seconds), 0.1, dtype="float32"), RATE)
            clips[one["id"]] = {"file": str(file), "seconds": seconds}
        return clips


def written(root, talker):
    grouped(root, NEWS)
    score(DAY, root=root, ask=rater())
    select(DAY, root=root, now=NOW)
    plan(DAY, root=root)
    return write(DAY, root=root, ask=talker)


def whole_day(root, talker, speak):
    written(root, talker)
    check_fit(DAY, root=root)
    voice(DAY, root=root, speak=speak)
    assemble(DAY, root=root)
    return package(DAY, root=root)


def test_a_day_hands_over_three_scripts_and_three_episodes(root):
    talker, speak = Talker(), Voice()
    result = whole_day(root, talker, speak)

    names = {file.name for file in result.folder.iterdir()}
    assert {"script.md", "episode.mp3", "podcast-script.md", "podcast-episode.mp3", "duo-script.md", "duo-episode.mp3"} <= names
    assert not any(name.startswith("clips") for name in names)  # the clips are deleted once the episodes exist
    # One plan serves both formats, and each segment is written once for each.
    assert talker.asked("plan") == ["plan"]
    assert len(talker.asked("podcast")) == len(talker.asked("duo")) == 4

    podcast = (result.folder / "podcast-script.md").read_text(encoding="utf-8")
    duo = (result.folder / "duo-script.md").read_text(encoding="utf-8")
    assert "# AIdea Daily: Tuesday, 6 October 2026 (one presenter)" in podcast and "**HOST:**" not in podcast
    assert "**HOST:** [surprised] So what happened?!" in duo and "**GUEST:** Lab shipped a thing." in duo
    assert "## 3. The biggest stories" in duo and "> **launch:** [Lab](" in duo
    assert "> - the shop" in podcast  # the writer's own examples are listed apart from the facts

    review = (result.folder / "review.md").read_text(encoding="utf-8")
    assert "## The longer episodes" in review and "`duo-episode.mp3`" in review
    assert "HOST in the voice of `voice/reference.wav`" in review
    for row in rows(root, db.format_scripts):
        assert row.audio_seconds > 0 and row.clips is None and row.note is None


def test_each_speaker_is_given_their_own_reference_voice_and_a_reaction_more_freedom(root):
    speak = Voice()
    whole_day(root, Talker(), speak)

    duo = next(call for call in speak.calls if any(one["text"].startswith("[surprised]") for one in call))
    by_text = {one["text"]: one for one in duo}
    assert by_text["[surprised] So what happened?!"]["reference"].endswith("reference.wav")
    assert by_text["Lab shipped a thing."]["reference"].endswith("reference-voice2-clean.wav")
    assert by_text["[surprised] So what happened?!"]["temperature"] == 1.0
    assert by_text["Lab shipped a thing."]["temperature"] == 0.5
    # The same words in the same voice are spoken once, however often the script says them.
    talk = sorted(text for text in by_text if "show notes" not in text and "Today's stories" not in text and "all for today" not in text)
    assert talk == ["It is available now.", "Lab shipped a thing.", "[surprised] So what happened?!"]
    # The host says the credits and the goodbye.
    credits = next(one for text, one in by_text.items() if text.startswith("Today's stories came from Lab and Press A."))
    assert credits["reference"].endswith("reference.wav")


def test_each_longer_script_ends_by_crediting_its_sources_once_however_often_it_is_checked(root):
    written(root, Talker())
    check_fit(DAY, root=root)
    assert runner.run_day(DAY, root=root, again=9, until=9, out=lambda _: None, checks=[])

    ending = "Today's stories came from Lab and Press A. Links to every source are in the show notes. That is all for today on AIdea Daily. Thanks for listening."
    for name, speaker in (("podcast", "PRESENTER"), ("duo", "HOST")):
        last = [row for row in rows(root, db.format_segments) if row.format == name][-1]
        assert [line["text"] for line in last.lines].count(ending) == 1
        assert last.lines[-1] == {"speaker": speaker, "text": ending, "credits": True}
    page = (root / "out" / DAY.isoformat() / "duo-script.md").read_text(encoding="utf-8")
    assert f"**HOST:** {ending}" in page.split("## Runtime")[0]
    assert all(row.flagged == [] for row in rows(root, db.format_scripts))


def test_a_figure_or_name_not_in_the_sources_is_kept_and_listed(root):
    wrong = {"lines": [{"speaker": "PRESENTER", "text": "Okay, here is the thing. Orion 4 costs $999 a month, says Zorblatt."}], "illustrations": []}
    talker = Talker(said={("podcast", "The biggest stories"): wrong})
    written(root, talker)
    result = check_fit(DAY, root=root)

    scripts = {row.format: row for row in rows(root, db.format_scripts)}
    assert [one["problems"] for one in scripts["podcast"].flagged] == [["number 999", "name Zorblatt"]]
    assert scripts["duo"].flagged == []
    page = (root / "out" / DAY.isoformat() / "podcast-script.md").read_text(encoding="utf-8")
    assert "Orion 4 costs $999 a month, says Zorblatt." in page.split("## Runtime")[0]  # kept in the script
    assert "## Sentences to check before using this (1)" in page and "(number 999, name Zorblatt)" in page
    assert "1 sentences to check" in rows(root, db.run_steps, step=9)[0].detail
    assert result.status == "ready"  # the regular episode is judged on its own check


def test_a_plan_that_forgets_or_repeats_a_story_still_tells_each_once():
    class Story:
        def __init__(self, story_id):
            self.story_id = story_id

    ranked = [Story(10), Story(11), Story(12)]
    made = tidy_plan({"segments": [
        {"kind": "stories", "title": "Big", "angle": "", "stories": [1, 1, 7], "words": 5000},
        {"kind": "stories", "title": "Again", "angle": "", "stories": [1], "words": 100},
        {"kind": "closing", "title": "Remember this", "angle": "", "stories": [2], "words": 10},
    ]}, ranked)

    assert [segment["kind"] for segment in made] == ["cold_open", "intro", "stories", "stories", "closing"]
    assert [segment["story_ids"] for segment in made] == [[], [], [10], [11, 12], []]
    assert made[2]["words"] == 1100 and made[-1]["title"] == "Remember this" and made[-1]["words"] == 80


def test_when_the_plan_cannot_be_asked_for_one_is_made_by_code(root):
    talker = Talker(plan=model.ModelError("the model's rate limit was reached"))
    written(root, talker)

    assert talker.asked("plan") == ["plan", "plan"]  # asked once more before giving up
    for name in ("podcast", "duo"):
        segments = [row for row in rows(root, db.format_segments) if row.format == name]
        assert [segment.kind for segment in segments] == ["cold_open", "intro", "stories", "closing"]
        assert len(segments[2].story_ids) == 2 and all(segment.lines for segment in segments)
    assert "made by code" in rows(root, db.format_scripts)[0].shortfall


def test_a_format_the_model_fails_on_is_left_out_and_the_rest_of_the_day_is_made(root):
    talker = Talker(said={("duo", "Introduction"): model.ModelError("the model stopped without a full answer")})
    result = whole_day(root, talker, Voice())

    names = {file.name for file in result.folder.iterdir()}
    assert {"episode.mp3", "podcast-script.md", "podcast-episode.mp3"} <= names
    assert "duo-script.md" not in names and "duo-episode.mp3" not in names
    assert talker.asked("duo") == ["duo: Cold open", "duo: Introduction", "duo: Introduction"]  # nothing after the failure
    review = (result.folder / "review.md").read_text(encoding="utf-8")
    assert "Not made: segment 2, Introduction, could not be written" in review
    assert result.status == "ready"


def test_a_run_stopped_while_writing_resumes_with_only_what_is_missing(root):
    talker = Talker(said={("duo", "The biggest stories"): RuntimeError("the PC was switched off")})
    with pytest.raises(RuntimeError):
        written(root, talker)

    again = Talker()
    write(DAY, root=root, ask=again)
    assert again.asked("plan") == [] and again.asked("podcast") == []
    assert again.asked("duo") == ["duo: The biggest stories", "duo: Closing takeaway"]
    # The segment after a break is told how the one before it ended.
    assert 'The segment before yours ended: "HOST: [surprised] So what happened?! GUEST: Lab shipped a thing. It is available now."' in again.requests[0][1]


def test_a_missing_reference_recording_leaves_that_episode_unspoken_and_says_so(root):
    (root / "voice" / "reference.wav").unlink()
    result = whole_day(root, Talker(), Voice())

    names = {file.name for file in result.folder.iterdir()}
    assert {"episode.mp3", "podcast-episode.mp3", "duo-script.md"} <= names and "duo-episode.mp3" not in names
    assert "No audio: not spoken: the reference recording is missing" in (result.folder / "review.md").read_text(encoding="utf-8")


def test_a_format_left_out_of_speak_gets_its_script_but_no_audio(root):
    edit_settings(root, 'speak = ["podcast", "duo"]', 'speak = ["podcast"]')
    speak = Voice()
    result = whole_day(root, Talker(), speak)

    names = {file.name for file in result.folder.iterdir()}
    assert {"episode.mp3", "podcast-script.md", "podcast-episode.mp3", "duo-script.md"} <= names and "duo-episode.mp3" not in names
    assert not any(one["text"].startswith("[surprised]") for call in speak.calls for one in call)  # no host line was spoken
    assert "No audio: not spoken: left out of `speak`" in (result.folder / "review.md").read_text(encoding="utf-8")


def test_repeating_the_voice_step_speaks_nothing_twice(root):
    written(root, Talker())
    check_fit(DAY, root=root)
    voice(DAY, root=root, speak=Voice())
    with db.connect(f"sqlite:///{(root / 'data' / 'local.db').as_posix()}").begin() as conn:
        conn.execute(db.run_steps.delete().where(db.run_steps.c.step == 10))

    again = Voice()
    voice(DAY, root=root, speak=again)
    assert not [one for call in again.calls for one in call if "reference" in one]


def test_a_line_is_spoken_in_pieces_and_a_short_piece_joins_its_neighbour():
    assert formats.split("Right. That is a lot of money for one lab. [laugh] And they said it twice!") == [
        "Right. That is a lot of money for one lab.", "[laugh] And they said it twice!"]
    assert formats.split("One thousand. At once.") == ["One thousand. At once."]
    assert formats.plain("[gasp] Wait, it broke its own computer?") == "Wait, it broke its own computer?"


def test_talk_is_not_mistaken_for_a_claim_but_a_figure_or_a_name_is():
    pool = Pool.of(["Lab shipped Orion 4 on Monday for $20 a month."])
    assert unverified("Okay, so I'll say it plainly: two things matter here.", pool) == []
    assert unverified("Imagine you pay $20 a month for Orion 4.", pool) == []
    assert unverified("Honestly, the Lab charges $25 a month.", pool) == ["number 25"]
    assert unverified("And then Acme copied it.", pool) == ["name Acme"]


def test_a_conversation_moves_faster_than_a_reader():
    pauses = {"sentence": 0.3, "paragraph": 0.6, "turn": 0.4, "reaction": 0.2, "segment": 1.1}
    def piece(speaker, turn, reaction=False, opens=False):
        return {"speaker": speaker, "turn": turn, "reaction": reaction, "opens_segment": opens}

    assert gap_after(piece("GUEST", 1), piece("GUEST", 1), pauses) == 0.3
    assert gap_after(piece("PRESENTER", 1), piece("PRESENTER", 2), pauses) == 0.6
    assert gap_after(piece("GUEST", 1), piece("HOST", 2), pauses) == 0.4
    assert gap_after(piece("GUEST", 1), piece("HOST", 2, reaction=True), pauses) == 0.2
    assert gap_after(piece("GUEST", 1), piece("HOST", 2, opens=True), pauses) == 1.1
    assert gap_after(piece("GUEST", 1), None, pauses) == 0.0
