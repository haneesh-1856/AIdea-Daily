"""Make the music bed: a 77-second loop in A minor at 100 beats a minute that the video repeats under the voice.

Like the sound kit, everything is synthesised here, so there is nothing to license. A warm pad, a sub bass, a soft
plucked arpeggio, and from bar 9 a quiet kick and hi-hat. The loop ends where it starts, so it repeats without a seam.

    .venv\\Scripts\\python.exe video\\make_music.py
"""

from pathlib import Path

import numpy
import soundfile

RATE = 48000
BPM = 100
BEAT = 60 / BPM
BAR = 4 * BEAT
BARS = 32
OUT = Path(__file__).parent / "public" / "music"
rng = numpy.random.default_rng(11)

# i - VI - III - VII in A minor, two bars each: Am, F, C, G (MIDI notes).
CHORDS = [[57, 60, 64, 69], [53, 57, 60, 65], [55, 60, 64, 67], [55, 59, 62, 67]]
ROOTS = [33, 29, 36, 31]
length = int(BARS * BAR * RATE)
t_all = numpy.arange(length) / RATE


def hz(note: float) -> float:
    return 440 * 2 ** ((note - 69) / 12)


def tone(freq: float, seconds: float, harmonics: int = 10, detune: float = 0.0) -> numpy.ndarray:
    """A soft saw: harmonics falling as 1/k^1.4, so it is warm rather than buzzy."""
    t = numpy.arange(int(seconds * RATE)) / RATE
    out = numpy.zeros_like(t)
    for k in range(1, harmonics + 1):
        if freq * k > 9000:
            break
        out += numpy.sin(2 * numpy.pi * freq * (1 + detune) * k * t + k) / k**1.4
    return out


def env(n: int, attack: float, release: float) -> numpy.ndarray:
    t = numpy.arange(n) / RATE
    return numpy.clip(t / attack, 0, 1) * numpy.clip((n / RATE - t) / release, 0, 1)


def place(track: numpy.ndarray, sound: numpy.ndarray, at: float) -> None:
    """Add a sound at a time; whatever runs past the end wraps to the start, which keeps the loop seamless."""
    start = int(at * RATE) % length
    end = start + len(sound)
    if end <= length:
        track[start:end] += sound
    else:
        track[start:] += sound[: length - start]
        track[: end - length] += sound[length - start :]


def lowpass(signal: numpy.ndarray, cutoff: float) -> numpy.ndarray:
    """A gentle low-pass done in one go in the frequency domain; circular, so it keeps the loop seamless."""
    spectrum = numpy.fft.rfft(signal)
    f = numpy.fft.rfftfreq(len(signal), 1 / RATE)
    return numpy.fft.irfft(spectrum / numpy.sqrt(1 + (f / cutoff) ** 4), len(signal))


def reverb(signal: numpy.ndarray, seconds: float = 2.2, mix: float = 0.35) -> numpy.ndarray:
    n = int(seconds * RATE)
    ir = rng.standard_normal(n) * numpy.exp(-numpy.arange(n) / RATE * 6.9 / seconds)
    ir = lowpass(numpy.concatenate([ir, numpy.zeros(length - n)]), 4000)
    wet = numpy.fft.irfft(numpy.fft.rfft(signal) * numpy.fft.rfft(ir), length)  # circular, like the rest
    return signal * (1 - mix) + wet / numpy.abs(wet).max() * numpy.abs(signal).max() * mix


def normal(x: numpy.ndarray) -> numpy.ndarray:
    return x / (numpy.abs(x).max() or 1)


def main() -> None:
    pad_l, pad_r = numpy.zeros(length), numpy.zeros(length)
    bass, arp, kick, hats = (numpy.zeros(length) for _ in range(4))
    for bar in range(0, BARS, 2):
        chord = (bar // 2) % 4
        span = 2 * BAR
        for note in CHORDS[chord]:
            n = int((span + 1.0) * RATE)
            e = env(n, 0.9, 1.4)
            place(pad_l, tone(hz(note), span + 1.0, detune=-0.0025)[:n] * e, bar * BAR)
            place(pad_r, tone(hz(note), span + 1.0, detune=0.0025)[:n] * e, bar * BAR)
        root = hz(ROOTS[chord])
        for beat in range(8):
            n = int(BEAT * 0.95 * RATE)
            t = numpy.arange(n) / RATE
            place(bass, numpy.sin(2 * numpy.pi * root * t) * numpy.exp(-t * 2.5) * env(n, 0.01, 0.08), bar * BAR + beat * BEAT)
        # A plucked arpeggio in sixteenths over the top two chord notes and the octave.
        notes = CHORDS[chord][1:] + [CHORDS[chord][1] + 12]
        for step in range(32):
            if step % 8 == 7:
                continue  # a gap each half bar so it breathes
            n = int(0.5 * RATE)
            t = numpy.arange(n) / RATE
            pluck = tone(hz(notes[step % len(notes)] + 12), 0.5, harmonics=4) * numpy.exp(-t * 9)
            place(arp, pluck * (0.7 + 0.3 * ((step % 4) == 0)), bar * BAR + step * BEAT / 4)
    for beat in range(BARS * 4):
        bar = beat // 4
        if bar < 8 or bar >= 30:
            continue  # the drums come in at bar 9 and drop out for the last two bars, before the loop starts over
        n = int(0.4 * RATE)
        t = numpy.arange(n) / RATE
        if beat % 2 == 0:
            freq = 48 + 70 * numpy.exp(-t * 30)
            place(kick, numpy.sin(2 * numpy.pi * numpy.cumsum(freq) / RATE) * numpy.exp(-t * 9), beat * BEAT)
        for half in (0, 0.5):
            m = int(0.05 * RATE)
            noise = rng.standard_normal(m) * numpy.exp(-numpy.arange(m) / RATE * 90)
            place(hats, noise * (1.0 if half else 0.55), (beat + half) * BEAT)
    hats = hats - lowpass(hats, 7000)  # high-pass: keep only the sizzle
    pad_l, pad_r = lowpass(pad_l, 1800), lowpass(pad_r, 1800)
    arp = reverb(lowpass(arp, 3500), 2.6, 0.45)
    pad_l, pad_r = reverb(pad_l), reverb(pad_r)
    # A slow swell over each two bars keeps the pad moving.
    swell = 0.85 + 0.15 * numpy.sin(2 * numpy.pi * t_all / (2 * BAR))
    mono = 0.55 * normal(bass) + 0.2 * normal(arp) + 0.28 * normal(kick) + 0.05 * normal(hats)
    left = 0.42 * normal(pad_l) * swell + mono
    right = 0.42 * normal(pad_r) * swell + mono
    stereo = numpy.stack([left, right], axis=1)
    stereo = numpy.tanh(stereo * 1.2) / numpy.tanh(1.2)  # soft limit
    stereo *= 0.89 / numpy.abs(stereo).max()
    OUT.mkdir(parents=True, exist_ok=True)
    soundfile.write(OUT / "bed.wav", stereo.astype("float32"), RATE, subtype="PCM_16")
    print(f"{BARS * BAR:.1f} s loop -> {OUT / 'bed.wav'}")


if __name__ == "__main__":
    main()
