import numpy

from steps.step10_voice.worker import clean, longest_pause, loudness

RATE = 24000


def tone(seconds: float, level: float = 0.3):
    t = numpy.arange(int(RATE * seconds)) / RATE
    return (level * numpy.sin(2 * numpy.pi * 150 * t)).astype("float32")


def hush(seconds: float, level: float = 0.0):
    return (level * numpy.random.default_rng(1).standard_normal(int(RATE * seconds))).astype("float32")


def test_a_breath_is_made_silent_and_long_silences_are_shortened():
    # speech, a breath (quiet noise) inside a long pause, speech, and silence at the end
    take = numpy.concatenate([hush(0.4), tone(1.0), hush(0.5), hush(0.4, 0.01), hush(1.0), tone(1.0), hush(0.6)])
    out = clean(take, RATE)
    # the breath is gone and the pause between the words is at most half a second; the edges are trimmed
    assert longest_pause(out, RATE) <= 0.52
    assert abs(len(out) / RATE - (2.0 + 0.5 + 0.05)) < 0.1
    middle = out[int(RATE * 1.05):int(RATE * 1.5)]
    assert numpy.abs(middle).max() < 1e-3


def test_speech_is_left_as_it_is():
    take = numpy.concatenate([tone(1.0), hush(0.3), tone(0.8, 0.2)])
    out = clean(take, RATE)
    assert len(out) == len(take)
    assert numpy.allclose(out, take)


def test_a_long_pause_and_a_shout_are_measured():
    calm = numpy.concatenate([tone(1.0, 0.1), hush(0.3), tone(1.0, 0.1)])
    shout = numpy.concatenate([tone(1.0, 0.1), hush(2.5), tone(1.0, 0.4)])
    assert longest_pause(calm, RATE) < 0.4
    assert 2.4 < longest_pause(shout, RATE) < 2.6
    # silence before the first sound and after the last does not count as a pause
    assert longest_pause(numpy.concatenate([hush(3.0), calm, hush(3.0)]), RATE) < 0.4
    assert loudness(shout, RATE) - loudness(calm, RATE) > 11
