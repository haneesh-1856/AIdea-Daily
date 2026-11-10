"""The pronunciation lexicon: tested spellings are used, untested or unreliable ones are not, and new names are listed."""

import importlib.util
import sys
from pathlib import Path

from steps.step10_voice import lexicon
from steps.step10_voice.step import spoken, untested_report

ROOT = Path(__file__).resolve().parents[2]


def entry(say, passes=5, **more):
    return {"say": say, "passes": passes, "of": 5, "tested": "2026-11-10", **more}


def test_the_lexicon_file_is_saved_and_read_back(tmp_path):
    (tmp_path / "voice").mkdir()
    entries = {"Huang": entry("Hwahng", sentence='She said "hi" to Huang.'), "Suno": {"status": "none", "best": "Soono", "passes": 2, "of": 5}}
    lexicon.save(tmp_path, entries)
    assert lexicon.load(tmp_path) == entries
    assert lexicon.load(tmp_path / "nowhere") == {}


def test_only_tested_spellings_are_used():
    says = lexicon.says({"A": entry("a"), "B": entry("b", passes=3), "C": {"status": "none", "best": "c", "passes": 5}, "D": {"passes": 5}})
    assert says == {"A": "a"}


def test_a_respelling_comes_out_once_the_longest_name_first_and_is_not_respelt_by_say():
    tested = {"Claude Code": entry("Clawd Kode"), "Claude": entry("Clawd"), "Huang": entry("Hwahng")}
    assert spoken("Claude Code and Claude's Huang.", {}, tested) == "Clawd Kode and Clawd's Hwahng."
    # [voice.say] still works for a word the lexicon does not have, and cannot touch a tested respelling.
    assert spoken("Claude and Orion.", {"Orion": "oh-RYE-un", "Clawd": "WRONG"}, tested) == "Clawd and oh-RYE-un."
    # A word inside another word, or hyphened to one, is left alone.
    assert spoken("Claudette and Claude-like.", {}, tested) == "Claudette and Claude-like."
    assert spoken("Claude Code ships in 1,600 places, 5%.", {}, tested).startswith("Clawd Kode ships in one thousand six hundred places")


def test_the_lexicon_changes_nothing_when_it_is_empty():
    assert spoken("Claude is 5% better.", {}, {}) == spoken("Claude is 5% better.") == "Claude is 5 percent better."


def test_names_not_yet_tested_are_listed_and_ordinary_words_are_not(tmp_path):
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "common-words.txt").write_text("the\nwas\nmonday\nsays\nreport\n", encoding="utf-8")
    texts = ["Huang says the report was late.", "Monday: Huang and Gizmodo and Anthropic. AWS and GPT also.", "Andrej Karpathy built SynthID."]
    names = dict(lexicon.untested(texts, {"Anthropic": entry("Ann Thropic")}, {"Karpathy": "x"}, tmp_path))
    assert names == {"Huang": 2, "Gizmodo": 1, "Andrej": 1, "SynthID": 1}


def test_without_a_word_list_nothing_is_listed(tmp_path):
    assert lexicon.untested(["Huang spoke."], {}, {}, tmp_path) == []


def test_the_review_sheet_lists_the_names_not_yet_tested():
    lines = untested_report(["Huang met Huang and Gizmodo."], {}, {}, ROOT)
    text = "\n".join(lines)
    assert "Names not yet tested" in text and "Huang (2)" in text and "Gizmodo" in text
    assert untested_report(["it was fine."], {}, {}, ROOT) == []


def search_tool():
    path = ROOT / "experiments" / "voice_bench" / "lexicon.py"
    spec = importlib.util.spec_from_file_location("lexicon_search", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lexicon_search"] = module
    spec.loader.exec_module(module)
    return module


def test_candidates_are_the_name_as_written_syllables_and_the_existing_entry():
    tool = search_tool()
    found, cost = tool.candidates("Federighi", "Fed-uh-REE-ghee", ["Federighi spoke."], llm=False)
    assert list(found)[:3] == ["Federighi", "Fed-uh-REE-ghee", "Fe-de-rig-hi"] and cost == 0
    assert found["Federighi"] == "as written" and found["Fed-uh-REE-ghee"] == "existing entry"
    assert tool.hyphenated("Pierre Stock") == "Pier-re Stock"


def test_a_take_is_right_when_nothing_found_wrong_concerns_the_name():
    tool = search_tool()
    assert tool.about('"huang" was heard as "wang"', "Huang", "Hwahng")
    assert tool.about('"hwahng" was not heard', "Huang", "Hwahng")
    assert not tool.about('"tweak" was heard as "tweet"', "Huang", "Hwahng")
    assert not tool.about(None, "Huang", "Hwahng")


def test_only_real_names_are_judged_against_their_own_spelling():
    tool = search_tool()
    assert all(tool.is_name(n) for n in ("Huang", "Pierre Stock", "Claude Code", "Ollama", "Claudes"))
    assert not any(tool.is_name(n) for n in ("AWS", "tpu", "404 Media", "Ep", "AIdea", "ElevenLabs", "robots.txt", "Show HN"))
