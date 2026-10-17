"""Make the small sound kit the edit uses on its cuts: whooshes, a low hit, a tick and a soft pulse.

Everything is synthesised here, so there is nothing to license.

    .venv\\Scripts\\python.exe video\\make_sfx.py
"""

from pathlib import Path

import numpy
import soundfile

RATE = 48000
OUT = Path(__file__).parent / "public" / "sfx"
rng = numpy.random.default_rng(7)


def envelope(n: int, attack: float, release: float) -> numpy.ndarray:
    t = numpy.linspace(0, 1, n)
    rise = numpy.clip(t / attack, 0, 1) ** 2
    fall = numpy.clip((1 - t) / release, 0, 1) ** 1.5
    return rise * fall


def sweep_filter(noise: numpy.ndarray, start_hz: float, end_hz: float) -> numpy.ndarray:
    """A one-pole low-pass whose cutoff glides, so noise sounds like air moving past."""
    out = numpy.zeros_like(noise)
    cutoffs = numpy.geomspace(start_hz, end_hz, len(noise))
    alphas = 1 - numpy.exp(-2 * numpy.pi * cutoffs / RATE)
    y = 0.0
    for i, (x, a) in enumerate(zip(noise, alphas)):
        y += a * (x - y)
        out[i] = y
    return out


def whoosh(seconds: float, start_hz: float, peak_hz: float, pan: float) -> numpy.ndarray:
    n = int(RATE * seconds)
    half = n // 2
    noise = rng.standard_normal(n)
    body = numpy.concatenate([sweep_filter(noise[:half], start_hz, peak_hz), sweep_filter(noise[half:], peak_hz, start_hz)])
    body *= envelope(n, 0.55, 0.45)
    body /= numpy.abs(body).max()
    left, right = body * (1 - pan), body * (1 + pan)
    return numpy.stack([left, right], axis=1) * 0.8


def hit(seconds: float = 1.2) -> numpy.ndarray:
    n = int(RATE * seconds)
    t = numpy.arange(n) / RATE
    freq = 38 + 90 * numpy.exp(-t * 18)  # a pitch drop makes it feel heavy
    sub = numpy.sin(2 * numpy.pi * numpy.cumsum(freq) / RATE) * numpy.exp(-t * 3.2)
    click = sweep_filter(rng.standard_normal(n), 6000, 300) * numpy.exp(-t * 40) * 3
    tail = sweep_filter(rng.standard_normal(n), 1200, 200) * numpy.exp(-t * 6) * 0.6
    body = sub + click + tail
    body /= numpy.abs(body).max()
    return numpy.stack([body, body], axis=1) * 0.9


def tick() -> numpy.ndarray:
    n = int(RATE * 0.09)
    t = numpy.arange(n) / RATE
    body = numpy.sin(2 * numpy.pi * 2400 * t) * numpy.exp(-t * 80) + numpy.sin(2 * numpy.pi * 1200 * t) * numpy.exp(-t * 60) * 0.5
    body /= numpy.abs(body).max()
    return numpy.stack([body, body], axis=1) * 0.6


def pulse() -> numpy.ndarray:
    """Two soft thumps, like the heartbeat in the logo."""
    n = int(RATE * 0.9)
    t = numpy.arange(n) / RATE
    beat = lambda at: numpy.sin(2 * numpy.pi * 55 * (t - at)) * numpy.exp(-numpy.clip(t - at, 0, None) * 14) * (t >= at)
    body = beat(0.0) + 0.7 * beat(0.22)
    body /= numpy.abs(body).max()
    return numpy.stack([body, body], axis=1) * 0.8


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    kit = {
        "whoosh-a.wav": whoosh(0.55, 300, 5000, -0.3),
        "whoosh-b.wav": whoosh(0.45, 500, 7000, 0.3),
        "whoosh-long.wav": whoosh(0.9, 200, 4000, 0.0),
        "hit.wav": hit(),
        "tick.wav": tick(),
        "pulse.wav": pulse(),
    }
    for name, audio in kit.items():
        soundfile.write(OUT / name, audio.astype("float32"), RATE)
    print(f"{len(kit)} sounds in {OUT}")


if __name__ == "__main__":
    main()
