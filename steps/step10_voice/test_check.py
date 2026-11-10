from pathlib import Path

import pytest

from steps.step10_voice.check import fault, recheck, words


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


@pytest.mark.parametrize("written, heard", [
    # ordinals
    ("It's Wednesday, 28 October 2026, and I'm glad you're here.", "It's Wednesday 28th October 2026 and I'm glad you're here."),
    ("The beta starts on October 23.", "The beta starts on October 23rd."),
    # hyphens and compound words
    ("The boot sector is hand-written assembly.", "The boot sector is handwritten assembly."),
    ("They're also upfront about the downsides.", "They're also up front about the down side."),
    ("The email service is Proton Mail.", "The email service is ProtonMail."),
    ("It is an iOS-only beta.", "It is an iOS only beta."),
    # British and American spelling
    ("Those are their characterisations.", "Those are their characterizations."),
    ("Both stories have that same flavour.", "Both stories have that same flavor."),
    ("There are sceptics of the colour scheme.", "There are skeptics of the color scheme."),
    ("The centre will analyse the data.", "The center will analyze the data."),
    ("The defence said the labelled files were fine.", "The defense said the labeled files were fine."),
    # units and sizes
    ("It runs on 64 GB of RAM.", "It runs on 64GB of RAM."),
    ("It runs on 64 GiB of RAM.", "It runs on 64 gigabytes of RAM."),
    ("Inputs stay under 64 MB in size.", "Inputs stay under 64 megabytes in size."),
    ("The model has 284B parameters in total.", "The model has 284 billion parameters in total."),
    ("The cache holds 256K tokens at most.", "The cache holds 256,000 tokens at most."),
    ("A 256 thousand token cache is used here.", "A 256K token cache is used here."),
    ("It runs 2.2x faster than before.", "It runs 2.2 times faster than before."),
    ("It reached 82% of users last week.", "It reached 82 percent of users last week."),
    ("It reached 82 per cent of users last week.", "It reached 82 percent of users last week."),
    # money
    ("It will cost £100m to build.", "It will cost 100 million pounds to build."),
    ("Meta plans a $95bn stock offering soon.", "Meta plans a $95 billion stock offering soon."),
    ("Meta plans a 95 billion dollar stock offering soon.", "Meta plans a $95bn stock offering soon."),
    ("Premium costs $2,599.99 a year.", "Premium costs 2,599 dollars and 99 cents a year."),
    ("It costs $0.07 per second here.", "It costs 7 cents per second here."),
    ("It costs $5.00 per month here.", "It costs $5 per month here."),
    ("It costs 5 euros per month here.", "It costs €5 per month here."),
    # figures in words, thousands, decimals
    ("It has 43,384 examples in all.", "It has forty-three thousand three hundred eighty-four examples in all."),
    ("Wait for twenty minutes before going.", "Wait for 20 minutes before going."),
    ("The score is 1.00000 on the test set.", "The score is 1 on the test set."),
    ("It scores 12.50 percent on the test.", "It scores 12.5 percent on the test."),
    ("It reaches 9.1 to 14.7 tokens per second.", "It reaches 9.1-14.7 tokens per second."),
    ("The model Qwen3.5-2B is small and fast.", "The model Qwen 3.5, 2 billion is small and fast."),
    ("Run v1.1 of the tool today.", "Run version 1.1 of the tool today."),
    ("It is S-1/A filing time again.", "It is S1A filing time again."),
    # contractions, case, punctuation
    ("Before, you'd just click.", "before you just click"),
    ("They are not equally solid, so I'll tell you.", "They're not equally solid so I will tell you."),
    ("It is U.S. policy for now.", "It is US policy for now."),
    # said alike
    ("Open weights cannot be cut off.", "Open waits cannot be cut off."),
    ("It would emit 570,000 tonnes of gas.", "It would emit 570,000 tons of gas."),
    # a name written its own way
    ("Elon wants Claude to work with Ollama today.", "Elon wants Clawed to work with Allama today."),
])
def test_a_difference_of_writing_only_is_not_a_fault(written, heard):
    assert fault(written, heard) is None


@pytest.mark.parametrize("written, spoken, heard", [
    ("Welcome to AIdea Daily.", "Welcome to I-dea Daily.", "Welcome to IDEA Daily."),
    ("Welcome to AIdea Daily.", "Welcome to I-dea Daily.", "Welcome to Idea Daily"),
    ("Anthropic says Claude is fast.", "Ann Thropic says Clawd is fast.", "Ann Thropic says Clawd is fast."),
    ("Anthropic says Claude is fast.", "Ann Thropic says Clawd is fast.", "Anthropic says Claude is fast."),
    ("It runs on DeepSeek today.", "It runs on Deep-Seek today.", "It runs on Deep Seek today."),
])
def test_a_clip_that_says_the_spoken_form_is_fine(written, spoken, heard):
    assert fault(written, heard, spoken) is None


def test_the_spoken_form_does_not_excuse_what_neither_says():
    assert fault("Welcome to AIdea Daily.", "Welcome to Idle Daily.", "Welcome to I-dea Daily.")


@pytest.mark.parametrize("written, heard", [
    # a wrong, dropped or added figure
    ("Premium costs $2,399 a year.", "Premium costs $2,499 a year."),
    ("It reached 82% of users in two weeks.", "It reached 82% of users."),
    ("It reached 82% of users in two weeks.", "It reached 28% of users in two weeks."),
    ("It reached 82% of users in two weeks.", "It reached 82% of users in three weeks."),
    ("The beta starts on October 23.", "The beta starts on October 29th."),
    ("Inputs stay under 64 MB in size.", "Inputs stay under 46MB in size."),
    ("Inputs stay under 64 MB in size.", "Inputs stay under 64 GB in size."),
    ("It will cost £100m to build.", "It will cost 10 million pounds to build."),
    ("Meta plans a $95bn stock offering soon.", "Meta plans a $95 million stock offering soon."),
    ("Meta plans a $95bn stock offering soon.", "Meta plans a $59 billion stock offering soon."),
    ("DeepSeek released Flash 1017 on Friday.", "DeepSeek released Flash 10 18 on Friday."),
    ("On June 26, 2026, they met.", "On June 26, 2021, they met."),
    ("It is an error rate of 0.00065%.", "It is an error rate of 0.065%."),
    ("A Ryzen 9 9955HX chip is in it.", "A Ryzen 9 9755HX chip is in it."),
    ("It rises from 66.8% to 92.4% overall.", "It rises from 92.4% to 66.8% overall."),
    ("It would emit 570,000 tonnes of gas.", "It would emit 507,000 tons of gas."),
    ("Two bills stand out.", "Three bills stand out."),
    ("It shipped in March.", "It shipped in March 2025."),
    ("Tested Qwen3.8-27B on a web page request.", "Tested Qwen 3.5, 27 billion on a web page request."),
    # a wrong or missing name
    ("Three House committees have asked Jensen Huang for a briefing.", "Three House committees have asked Jensen Wang for a briefing."),
    ("Three House committees have asked Jensen Huang for a briefing.", "Three House committees have asked Jensen Hong for a briefing."),
    ("Andrej Karpathy says he built a video site in a weekend.", "Andrej Kaipathy says he built a video site in a weekend."),
    ("Andrej Karpathy says he built a video site in a weekend.", "Andrej says he built a video site in a weekend."),
    ("Anthropic says Claude is used by many developers now.", "Anthropic says Clog is used by many developers now."),
    ("Wired's point is narrower.", "Wide's point is narrower."),
    # a wrong word, a changed meaning
    ("Claims are cheap, and some are very hard to check.", "Games are cheap, and some are very hard to check."),
    ("Claims are cheap, and some are very hard to check.", "Flames are cheap, and some are very hard to check."),
    ("The boot sector is hand-written assembly.", "The boat sector is hand-written assembly."),
    ("Open weights cannot be cut off by anyone.", "Open weeds cannot be cut off by anyone."),
    ("The model did not pass the test.", "The model did pass the test."),
    ("The service is not free for anyone.", "The service is free for anyone."),
    ("He said the price rose sharply.", "She said the price rose sharply."),
    ("Who confirmed the result?", "or confirm the result."),
    # a clause or an ending missing, a stutter, extra speech
    ("Waymo runs in 15 cities and faces opposition from unions and others.", "Waymo runs in 15 cities and faces opposition from unions."),
    ("Both stories have that flavour, with a flood of text, the other with a box on wheels.", "Both stories have that flavor, with a flood of text."),
    ("Who confirmed the result of the vote on Friday?", "Who who confirmed the result of the vote on Friday?"),
    ("The team shipped it on Friday after a long wait.", "The team shipped it on Friday after after a long wait."),
    ("That is all for today. Thanks for listening.", "That is all for today. Thanks for listening. Thank you for watching."),
    ("Before, you'd just click.", "before."),
    ("It is built on a small model.", ""),
    # small words may slip, but not many
    ("Then there is price, and google says it dropped the price a lot this year for everyone.", "Than this price, google said it dropped price lot this year everyone."),
])
def test_a_real_error_is_a_fault(written, heard):
    assert fault(written, heard)


@pytest.mark.parametrize("text, tokens", [
    ("28th", ["28"]),
    ("$30.50", ["30", "dollar", "50", "cent"]),
    ("£100m", ["100000000", "pound"]),
    ("64GB", ["64", "gb"]),
    ("43,384", ["43384"]),
    ("forty-seven thousand", ["47000"]),
    ("twenty one", ["21"]),
    ("five hundred seventy thousand", ["570000"]),
    ("2.2x", ["2.2", "times"]),
    ("it's, you'd, Wired's", ["it", "is", "you", "would", "wired"]),
])
def test_text_is_written_as_plain_tokens(text, tokens):
    assert words(text) == tokens


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
