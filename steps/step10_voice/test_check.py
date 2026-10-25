from pathlib import Path

import pytest

from steps.step10_voice.check import fault, recheck


@pytest.mark.parametrize("sentence, heard", [
    ("Ollama now runs on Windows, said the team.", "Allama now runs on Windows, said the team."),
    ("It reached 82% of users in two weeks.", "It reached 82 percent of users in 2 weeks."),
    ("DeepSeek released Flash 1017 on Friday.", "DeepSeek released Flash 10 17 on Friday."),
    ("Premium costs $2,399 a year.", "Premium costs $2399 a year."),
    ("First up, Claude for Google Workspace.", "First up, Clawed for Google Workspace."),
])
def test_a_name_spelled_its_own_way_passes(sentence, heard):
    assert fault(sentence, heard) is None


@pytest.mark.parametrize("sentence, heard, found", [
    ("It works with agents from Anthropic, OpenAI and Meta, and it is free.", "It works with agents from Anthropic, OpenAI and Meta.", "not heard"),
    ("Premium costs $2,399 and ships in March.", "Premium costs $2,039 and ships in March.", "2399"),
    ("So what are governments telling people?", "So what are governments telling people? Telling people?", "said twice"),
    ("The model was trained on menus, receipts and posters from many shops.",
     "The model was trained on menus, receipts and and posters posters from many many shops shops.", "extra words"),
    ("Researchers examined histories donated by 80 users.", "", "nothing was heard"),
])
def test_a_wrong_clip_is_found(sentence, heard, found):
    assert found in fault(sentence, heard)


class Takes:
    """Stands in for the voice and for Whisper: each sentence is heard as the next answer in its list."""

    def __init__(self, answers):
        self.answers = {key: list(value) for key, value in answers.items()}
        self.spoken = []

    def speak(self, items, voice, folder):
        self.spoken.append([item["id"] for item in items])
        made = {}
        for item in items:
            file = folder / f"{item['id']:04d}.wav"
            file.write_text(self.answers[item["id"]][0], encoding="utf-8")
            made[item["id"]] = {"file": str(file), "seconds": 2.0}
        return made

    def listen(self, clips):
        heard = {}
        for clip in clips:
            heard[clip["id"]] = {"text": Path(clip["file"]).read_text(encoding="utf-8")}
            self.answers[clip["id"]].pop(0)
        return heard


def made_by(takes, items, folder):
    return takes.speak(items, {}, folder)


def test_a_wrong_clip_is_spoken_again_and_the_better_take_kept(tmp_path):
    items = [{"id": 1, "text": "x", "plain": "The team shipped it on Friday after a long wait."},
             {"id": 2, "text": "y", "plain": "Nothing else changed this week at the lab."}]
    takes = Takes({1: ["The team shipped it.", "The team shipped it on Friday after a long wait."],
                   2: ["Nothing else changed this week at the lab."]})
    made = made_by(takes, items, tmp_path)
    found = recheck(items, made, takes.speak, takes.listen, {}, tmp_path)
    assert takes.spoken[1:] == [[1]]
    assert found == [{"id": 1, "text": items[0]["plain"], "was": found[0]["was"], "left": None}]
    assert Path(made[1]["file"]).read_text(encoding="utf-8").endswith("long wait.")
    assert sorted(file.name for file in tmp_path.iterdir()) == ["0001.wav", "0002.wav"]


def test_a_worse_retake_is_thrown_away_and_the_clip_listed(tmp_path):
    items = [{"id": 1, "text": "x", "plain": "The team shipped it on Friday after a long wait."}]
    takes = Takes({1: ["The team shipped it on Friday.", "The team.", "The team."]})
    made = made_by(takes, items, tmp_path)
    found = recheck(items, made, takes.speak, takes.listen, {}, tmp_path, rounds=2)
    assert len(takes.spoken) == 3
    assert Path(made[1]["file"]).read_text(encoding="utf-8") == "The team shipped it on Friday."
    assert found[0]["left"]
    assert [file.name for file in tmp_path.iterdir()] == ["0001.wav"]
