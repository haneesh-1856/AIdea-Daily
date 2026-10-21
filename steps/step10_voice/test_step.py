from pathlib import Path

import numpy
import pytest
import soundfile

from common import db, runlog
from common.settings import database_url
from steps.step05_score.step import score
from steps.step06_select.step import select
from steps.step07_plan.step import plan
from steps.step08_write.step import write
from steps.step09_check_fit.step import check_fit
from steps.step10_voice.step import VoiceError, phrases, spoken, voice
from steps.step11_assemble.step import assemble
from steps.step12_package.step import package
from steps.testkit import DAY, LINKING, NOW, STORY, edit_settings, fake_web, grouped, item, make_root, rater, rows, writer

SOURCES = [
    item("Lab", "primary", title="Lab ships Orion 4", summary="Orion 4 has 12 billion parameters and costs $20 a month, up 40%."),
    item("Press A", title="Lab ships a thing"), item("Press B", title="Lab ships a thing"),
]
RATE = 8000


@pytest.fixture
def root(tmp_path, monkeypatch):
    fake_web(monkeypatch)
    made = make_root(tmp_path, monkeypatch)
    edit_settings(made, "enabled = false", "enabled = true")
    return made


class FakeVoice:
    """Stands in for the voice model: every sentence becomes a tone lasting a third of a second per word.
    `bad` maps a piece of text to the answers to give for it, in turn: an error message, or a length in seconds."""

    def __init__(self, bad=None):
        self.bad = {piece: list(answers) for piece, answers in (bad or {}).items()}
        self.calls = []  # the sentences of each call

    def __call__(self, sentences, settings, folder):
        self.calls.append([one["text"] for one in sentences])
        folder.mkdir(parents=True, exist_ok=True)
        clips = {}
        for one in sentences:
            answers = next((answers for piece, answers in self.bad.items() if piece in one["text"]), None)
            answer = answers.pop(0) if answers else None
            if isinstance(answer, str):
                clips[one["id"]] = {"error": answer}
                continue
            seconds = answer if answer is not None else len(one["text"].split()) / 3
            file = folder / f"{one['position']:04d}.wav"
            soundfile.write(file, numpy.full(int(RATE * seconds), 0.1, dtype="float32"), RATE)
            clips[one["id"]] = {"file": str(file), "seconds": seconds}
        return clips


def checked(root, stories=None, linking=None):
    score(DAY, root=root, ask=rater())
    select(DAY, root=root, now=NOW)
    plan(DAY, root=root)
    write(DAY, root=root, ask=writer(stories, linking))
    return check_fit(DAY, root=root)


ORION = {"launch": dict(STORY, headline="Lab ships Orion 4.", what_happened="Lab shipped Orion 4. It costs $20 a month, up 40%.")}


def test_every_spoken_line_becomes_a_clip_in_order_with_its_pause(root):
    grouped(root, {"launch": SOURCES})
    started = checked(root, ORION)
    fake = FakeVoice()
    result = voice(DAY, root=root, speak=fake)

    # The brief version is not spoken, because the story is told in full.
    assert fake.calls == [[
        "Good morning.", "Here is the AI news.",
        "Lab ships Orion 4.",
        "Our top story today.", "launch.",
        "Lab shipped Orion 4.", "It costs 20 dollars a month, up 40 percent.",
        "Press B disagrees.",
        "That is all for today.",
        "Today's stories came from Lab, Press A and Press B.", "Links to every source are in the show notes.", "Thanks for listening today.",
    ]]
    found = rows(root, db.clips)
    assert (result.state, result.clips) == ("voiced", 12)
    # sentence, then into the headlines, then into the stories, the cue runs on into the title, part, sentence, part,
    # then into the closing, the end
    assert [clip.pause_after for clip in found] == [0.55, 1.0, 1.0, 0.55, 0.8, 0.55, 0.8, 1.0, 1.0, 0.55, 0.55, 0.0]
    assert all(Path(clip.file).exists() for clip in found)
    assert result.seconds == pytest.approx(sum(clip.seconds + clip.pause_after for clip in found))
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.next_step(conn, started.run_id) == 11
    text = result.report.read_text(encoding="utf-8")
    assert "| It costs $20 a month, up 40%. | It costs 20 dollars a month, up 40 percent. |" in text


@pytest.mark.parametrize("written, said", [
    ("It raised $300 million of a $1.8 billion round.", "It raised 300 million dollars of a 1.8 billion dollar round."),
    ("A $4B deal, $900M in revenue, $20 a month.", "A 4 billion dollar deal, 900 million dollars in revenue, 20 dollars a month."),
    ("A 501B model with 23B active, 270M for text, an 8K window.", "A 501 billion model with 23 billion active, 270 million for text, an 8 thousand window."),
    ("It scores 82% and 61.7 %.", "It scores 82 percent and 61.7 percent."),
    ("Up to 6x smaller, on DeepSWE v1.1.", "Up to 6 times smaller, on Deep-SWE version 1.1."),
    ("DeepSeek V4.1 Flash beats DSv4 and V3.", "Deep-Seek version 4.1 Flash beats DS version 4 and version 3."),
    ("It needs 191MB of RAM, or 8 GB for the full model.", "It needs 191 megabytes of RAM, or 8 gigabytes for the full model."),
    ("SynthID, OpenAI, ChatGPT and textGrain are on GitHub with WebGPU.", "Synth-ID, Open-AI, Chat-GPT and text-Grain are on Git-Hub with Web-GPU."),
    ("NVIDIA GPUs, the EU AI Act, MTEB and Lindsay McCallum.", "NVIDIA GPUs, the EU AI Act, MTEB and Lindsay McCallum."),
    ("Reflection Beam - 501B-A23B American Open Model", "Reflection Beam - 501 billion A23B American Open Model"),
    ("[AINews] Research & policy, ~5 minutes.", "AINews Research and policy, about 5 minutes."),
    ("GPT-5.5 and Mistral Large 4 on 6 October 2026.", "GPT-5.5 and Mistral Large 4 on 6 October 2026."),
    # The comma after an amount stays a comma, ranges are "to", and cents are said as cents.
    ("Premium at $30, Super at $100.", "Premium at 30 dollars, Super at 100 dollars."),
    ("It raised $8-9 million, or $1.5–2B.", "It raised 8 to 9 million dollars, or 1.5 to 2 billion dollars."),
    ("From $3,199.99 to $6,999.99, and $2,599.99.", "From three thousand one hundred ninety-nine dollars and 99 cents to six thousand nine hundred ninety-nine dollars and 99 cents, and two thousand five hundred ninety-nine dollars and 99 cents."),
    ("He was charged $504.00 USD for $5.04 and $1.5 billion.", "He was charged 504 dollars for 5 dollars and 4 cents and 1.5 billion dollars."),
    ("Under $0.20 per task, $0.01 a call, a $0.50 fee.", "Under 20 cents per task, 1 cent a call, a 50 cent fee."),
    ("The $2,399 is a start; the $36,864 bounty.", "The two thousand three hundred ninety-nine dollars is a start; the thirty-six thousand eight hundred sixty-four dollar bounty."),
    ("The 85 to $95,000 range, or 85 to $95,000.", "The 85 to ninety-five thousand dollar range, or 85 to ninety-five thousand dollars."),
    # A four-figure code is said in pairs; years, round hundreds, amounts and decimals are not.
    ("Deepseek-V4.1-Flash-1017 and GPT-5.6 on 18-core state-of-the-art chips.", "Deepseek version 4.1 Flash 10 17 and GPT-5.6 on 18-core state-of-the-art chips."),
    ("147,451 rows, 1,000,000 calls and 2.5 million.", "one hundred forty-seven thousand four hundred fifty-one rows, one million calls and 2.5 million."),
    ("Black Box: The Chatbots | Ep 6 - podcast.", "Black Box: The Chatbots, Ep 6 - podcast."),
    ("Flash 1017 on port 8081 with an RTX 4060 and model 1005.", "Flash 10 17 on port 80 81 with an RTX 40 60 and model 10 oh 5."),
    ("In 2026 and 1999, 1500 GPUs, 1600 dollars, 13.60 and 1,600 logs.", "In 2026 and 1999, 1500 GPUs, 1600 dollars, 13.60 and one thousand six hundred logs."),
    # Found on 2026-10-20: a date's month, milliseconds, a range of times, and a no-break hyphen.
    ("Beta on Oct. 20, 2026, and Sept 3; not in Dec or Mar.", "Beta on October 20, 2026, and September 3; not in Dec or Mar."),
    ("It takes 10 ms, 1 ms or 0.5ms, and runs 4–8x faster.", "It takes 10 milliseconds, 1 millisecond or 0.5 milliseconds, and runs 4 to 8 times faster."),
    ("Coding in low‑resource languages.", "Coding in low-resource languages."),
    # Found on 2026-10-21: the times sign, tiny prices, rates, GiB, and code.
    ("It decodes 5–6.5× faster, and 21.5 × on Qwen.", "It decodes 5 to 6.5 times faster, and 21.5 times on Qwen."),
    ("It costs $0.0035/min, a $0.005 fee, or 61.3 tokens/s.", "It costs 0.35 cents per minute, a 0.5 cent fee, or 61.3 tokens per second."),
    ("It peaks at 8 GiB, not 270GiB.", "It peaks at 8 gigabytes, not 270 gigabytes."),
    ("Load with device_map or pipe.to, e.g. torch_xla, at 3.8 and U.S. sites.", "Load with device map or pipe dot to, for example torch xla, at 3.8 and U.S. sites."),
    ("Use F.scaled_mm, Otter.ai or stateglobe.com.", "Use F dot scaled mm, Otter dot A I or stateglobe dot com."),
])
def test_figures_and_symbols_are_written_the_way_they_are_said(written, said):
    assert spoken(written) == said


def test_a_word_to_say_differently_is_not_changed_inside_an_amount():
    say = {"Claude": "Clawd", "3M": "three M"}
    assert spoken("Claude's maker and 3M paid $3M.", say) == "Clawd's maker and three M paid 3 million dollars."


@pytest.mark.parametrize("sentence, pieces", [
    ("It scores 82 percent on a test.", ["It scores 82 percent on a test."]),
    ("On a security test, where a model has to reproduce a real vulnerability and then patch it, it scores 82 percent.",
     ["On a security test,", "where a model has to reproduce a real vulnerability and then patch it,", "it scores 82 percent."]),
    ("Google DeepMind, Meta and the startup Isomorphic Labs are jointly investing 300 million dollars in an initiative led by Biohub, the nonprofit founded by Mark Zuckerberg and his wife, Priscilla Chan.",
     ["Google DeepMind, Meta and the startup Isomorphic Labs are jointly investing 300 million dollars in an initiative led by Biohub,",
      "the nonprofit founded by Mark Zuckerberg and his wife, Priscilla Chan."]),
    ("It reported 1,674 points, 1,003 comments and a score of 61.7 percent on the main test it ran this week.",
     ["It reported 1,674 points,", "1,003 comments and a score of 61.7 percent on the main test it ran this week."]),  # not split inside 1,674
])
def test_a_long_sentence_is_spoken_phrase_by_phrase_and_a_short_one_whole(sentence, pieces):
    assert phrases(sentence, longest=12) == pieces
    assert " ".join(phrases(sentence, longest=12)) == sentence  # nothing is lost or changed


def test_a_word_the_voice_gets_wrong_is_said_the_way_the_settings_give(root):
    edit_settings(root, "[voice.say]\n", '[voice.say]\n"Orion" = "oh-RYE-un"\n"Lab" = "the Lab"\n')
    grouped(root, {"launch": SOURCES})
    checked(root, ORION)
    fake = FakeVoice()
    voice(DAY, root=root, speak=fake)

    assert "the Lab shipped oh-RYE-un 4." in fake.calls[0]
    # The script itself is untouched.
    assert "Lab shipped Orion 4." in [row.text for row in rows(root, db.script_lines)]


def test_a_failed_or_misshapen_clip_is_spoken_once_more(root):
    grouped(root, {"launch": SOURCES})
    checked(root, ORION)
    # One sentence errors the first time; another comes back 60 seconds long for 4 words.
    fake = FakeVoice({"Lab shipped Orion 4.": ["out of memory"], "That is all for today.": [60.0]})
    result = voice(DAY, root=root, speak=fake)

    assert result.state == "voiced" and len(fake.calls) == 2
    assert fake.calls[1] == ["Lab shipped Orion 4.", "That is all for today."]
    assert "| Sentences spoken a second time | 2 |" in result.report.read_text(encoding="utf-8")


def test_a_sentence_that_fails_twice_stops_the_run_and_a_rerun_speaks_only_what_is_missing(root):
    grouped(root, {"launch": SOURCES})
    started = checked(root, ORION)
    with pytest.raises(VoiceError, match='1 sentences could not be spoken.*"Lab shipped Orion 4." \\(out of memory\\)'):
        voice(DAY, root=root, speak=FakeVoice({"Lab shipped Orion 4.": ["out of memory", "out of memory"]}))
    with db.connect(database_url(root)).connect() as conn:
        assert runlog.next_step(conn, started.run_id) == 10
    assert len(rows(root, db.clips)) == 11  # the good clips are kept

    fake = FakeVoice()
    result = voice(DAY, root=root, speak=fake)
    assert fake.calls == [["Lab shipped Orion 4."]]
    assert (result.state, result.clips) == ("voiced", 12)


def test_the_step_is_passed_over_when_voice_is_off_or_the_episode_is_held(tmp_path, monkeypatch):
    fake_web(monkeypatch)
    (tmp_path / "off").mkdir()
    (tmp_path / "held").mkdir()
    off = make_root(tmp_path / "off", monkeypatch)  # voice is off in a test's settings unless switched on
    grouped(off, {"launch": SOURCES})
    checked(off, ORION)
    fake = FakeVoice()
    result = voice(DAY, root=off, speak=fake)
    assert (result.state, fake.calls) == ("skipped", [])
    assert "Voice is switched off in settings." in result.report.read_text(encoding="utf-8")

    held = make_root(tmp_path / "held", monkeypatch)
    edit_settings(held, "enabled = false", "enabled = true")
    grouped(held, {"launch": SOURCES})
    bad = "Lab shipped Orion 4. It costs $25 a month. It costs $30 a year. It costs $35 a week. It is out now. It has 12 billion parameters."
    assert checked(held, {"launch": dict(STORY, what_happened=bad)}).status == "held"
    result = voice(DAY, root=held, speak=fake)
    assert (result.state, fake.calls) == ("skipped", [])
    assert "The episode is held" in result.report.read_text(encoding="utf-8")


def test_the_clips_are_joined_into_one_episode_file_and_then_deleted(root):
    grouped(root, {"launch": SOURCES})
    checked(root, ORION)
    spoke = voice(DAY, root=root, speak=FakeVoice())
    result = assemble(DAY, root=root)

    audio, rate = soundfile.read(result.folder / "episode.mp3")
    assert len(audio) / rate == pytest.approx(spoke.seconds, abs=0.2)
    assert not any(Path(clip.file).exists() for clip in rows(root, db.clips))  # the timings stay, the clip files go
    episode, = rows(root, db.episodes)
    assert episode.audio_seconds == pytest.approx(spoke.seconds, abs=0.05)
    assert f"and an episode of {spoke.seconds / 60:.1f} minutes" in result.report.read_text(encoding="utf-8")
    review = (package(DAY, root=root).folder / "review.md").read_text(encoding="utf-8")
    assert f"- `episode.mp3`: the spoken episode, {spoke.seconds / 60:.1f} minutes" in review


def test_it_needs_step_nine_first_and_does_not_run_twice(root):
    grouped(root, {"launch": SOURCES})
    score(DAY, root=root, ask=rater())
    with pytest.raises(VoiceError, match="Run step 9 first"):
        voice(DAY, root=root, speak=FakeVoice())
    select(DAY, root=root, now=NOW)
    plan(DAY, root=root)
    write(DAY, root=root, ask=writer(ORION))
    check_fit(DAY, root=root)
    voice(DAY, root=root, speak=FakeVoice())
    fake = FakeVoice()
    again = voice(DAY, root=root, speak=fake)
    assert (again.state, again.clips, fake.calls) == ("already_done", 12, [])
