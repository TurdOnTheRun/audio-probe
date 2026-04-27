#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 48_000
DURATION_SECONDS = 2.0
AMPLITUDE = 0.5


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic audio-probe fixtures.")
    parser.add_argument("--out", default="fixtures", help="output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    t = np.arange(int(SAMPLE_RATE * DURATION_SECONDS), dtype=np.float64) / SAMPLE_RATE
    rng = np.random.default_rng(42)

    write(out_dir / "sine-100hz.wav", AMPLITUDE * np.sin(2.0 * np.pi * 100.0 * t))
    write(out_dir / "sine-1000hz.wav", AMPLITUDE * np.sin(2.0 * np.pi * 1000.0 * t))
    write(out_dir / "sine-8000hz.wav", AMPLITUDE * np.sin(2.0 * np.pi * 8000.0 * t))
    write(out_dir / "noise-white.wav", 0.2 * rng.standard_normal(t.size))
    write(out_dir / "noise-pink.wav", pink_noise(rng, t.size) * 0.2)
    write(out_dir / "pulse.wav", pulse(t))
    write(out_dir / "click-loop.wav", click_loop(t))
    write(out_dir / "sustained-pad.wav", sustained_pad(t))
    write(out_dir / "impulse.wav", impulse(t.size))
    return 0


def write(path: Path, samples: np.ndarray) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    sf.write(path, clipped, SAMPLE_RATE, subtype="PCM_24")


def pink_noise(rng: np.random.Generator, size: int) -> np.ndarray:
    white = rng.standard_normal(size)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(size, d=1.0 / SAMPLE_RATE)
    scale = np.ones_like(freqs)
    nonzero = freqs > 0
    scale[nonzero] = 1.0 / np.sqrt(freqs[nonzero])
    pink = np.fft.irfft(spectrum * scale, n=size)
    pink /= np.max(np.abs(pink))
    return pink


def pulse(t: np.ndarray) -> np.ndarray:
    samples = np.zeros_like(t)
    for start in (0.25, 0.75, 1.25, 1.75):
        mask = (t >= start) & (t < start + 0.08)
        samples[mask] = 0.8 * np.sin(2.0 * np.pi * 1000.0 * (t[mask] - start))
    return samples


def click_loop(t: np.ndarray) -> np.ndarray:
    samples = np.zeros_like(t)
    for start in np.arange(0.1, DURATION_SECONDS, 0.2):
        index = int(start * SAMPLE_RATE)
        samples[index : index + 2] = [0.9, -0.9]
    return samples


def sustained_pad(t: np.ndarray) -> np.ndarray:
    attack = np.clip(t / 0.25, 0.0, 1.0)
    release = np.clip((DURATION_SECONDS - t) / 0.4, 0.0, 1.0)
    envelope = np.minimum(attack, release)
    signal = (
        0.35 * np.sin(2.0 * np.pi * 220.0 * t)
        + 0.2 * np.sin(2.0 * np.pi * 330.0 * t)
        + 0.12 * np.sin(2.0 * np.pi * 440.0 * t)
    )
    return envelope * signal


def impulse(size: int) -> np.ndarray:
    samples = np.zeros(size, dtype=np.float64)
    samples[size // 2] = 1.0
    return samples


if __name__ == "__main__":
    raise SystemExit(main())
