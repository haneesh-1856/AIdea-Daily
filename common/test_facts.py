import pytest

from common.facts import Pool, numbers_in, unsupported
from common.text import sentences


@pytest.mark.parametrize("text, values", [
    ("$900M in revenue", {900e6}),
    ("900 million dollars", {900e6}),
    ("nine hundred million dollars", {900e6}),
    ("a 4 billion round, or $4B, or 4bn", {4e9}),
    ("1,674 points and 1,001 comments", {1674, 1001}),
    ("GPT-5.4 nano costs $0.20", {5.4, 0.20}),
    ("up 3.5% from 40 percent", {3.5, 40}),
    ("a 501B-A23B model with 1T parameters", {501e9, 1e12}),
    ("on October 6th, 2026", {6, 2026}),
    ("twenty-five labs and two hundred and five papers", {25, 205}),
    ("two and three models", {2, 3}),
    ("one of the labs, and a hundred others", {100}),
    ("one hundred fifty thousand", {150000}),
    ("version 2 of the 12B model", {2, 12e9}),
    ("no figures here", set()),
])
def test_numbers_are_read_in_every_written_form(text, values):
    assert numbers_in(text) == values


SOURCE = Pool.of([
    "Mistral AI released Mistral Large 4 on Oct. 6, a model with 1 trillion parameters.",
    "Chief executive Arthur Mensch said it scored 78.4% on SWE-bench Verified.",
    "TechCrunch", "The Verge",
])


@pytest.mark.parametrize("sentence", [
    "Mistral released Mistral Large 4, a model with 1T parameters.",
    "It has one trillion parameters.",
    "Mensch said it scored 78.4 percent on SWE-bench Verified.",
    "The release came on October 6.",
    "However, The Verge was less sure.",
    "Notably, TechCrunch calls it a model for AI labs.",
    "Mistral's model is the company's largest.",
    "Arthur Mensch is the chief executive.",
    "One model was released.",
    "TechCrunch calls it an AI-built, Mistral-made model for SWE-bench.",
])
def test_a_sentence_built_from_the_source_passes(sentence):
    assert unsupported(sentence, SOURCE) == []


@pytest.mark.parametrize("sentence, problems", [
    ("It has 2 trillion parameters.", ["number 2e+12"]),
    ("It scored 87.4% on SWE-bench Verified.", ["number 87.4"]),
    ("Mistral Large 5 was released.", ["number 5"]),
    ("Sam Altman welcomed the release.", ["name Sam", "name Altman"]),
    ("The release came on November 6.", ["name November"]),
    ("OpenAI has not responded.", ["name OpenAI"]),
    ("It beats GPT-5.5 on SWE-bench Verified.", ["number 5.5", "name GPT-5.5"]),
    ("The three founders left.", ["number 3"]),
])
def test_anything_not_in_the_source_is_named(sentence, problems):
    assert unsupported(sentence, SOURCE) == problems


def test_text_is_split_into_sentences_without_breaking_numbers_or_initials():
    text = 'Mistral Large 4 scored 78.4% on a test. "It is our best," said A. Mensch. The U.S. launch is next! Is it open? Yes.'
    assert sentences(text) == [
        "Mistral Large 4 scored 78.4% on a test.",
        '"It is our best," said A. Mensch.',
        "The U.S. launch is next!",
        "Is it open?",
        "Yes.",
    ]
    assert sentences('It said the model "resolved 100 problems." Then it stopped. He called it "huge" (twice.) Yes.') == [
        'It said the model "resolved 100 problems."', "Then it stopped.", 'He called it "huge" (twice.)', "Yes.",
    ]
    assert sentences("") == [] and sentences(None) == []
