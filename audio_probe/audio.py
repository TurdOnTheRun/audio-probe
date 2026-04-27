from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class AudioData:
    path: Path
    samples: np.ndarray
    sample_rate: int

    @property
    def frames(self) -> int:
        return int(self.samples.shape[0])

    @property
    def channels(self) -> int:
        return int(self.samples.shape[1])

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate if self.sample_rate else 0.0

    @property
    def mono(self) -> np.ndarray:
        if self.channels == 1:
            return self.samples[:, 0]
        return np.mean(self.samples, axis=1)


@dataclass(frozen=True)
class TimeWindow:
    start: float
    end: float | None

    def as_json(self, duration_seconds: float) -> dict[str, float]:
        return {
            "start": round_float(self.start),
            "end": round_float(self.resolved_end(duration_seconds)),
        }

    def resolved_end(self, duration_seconds: float) -> float:
        return duration_seconds if self.end is None else self.end


def round_float(value: float, digits: int = 6) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == -0.0 else rounded


def load_audio(path: str | Path) -> AudioData:
    audio_path = Path(path)
    samples, sample_rate = sf.read(audio_path, always_2d=True, dtype="float64")
    return AudioData(path=audio_path, samples=samples, sample_rate=int(sample_rate))


def file_info(path: str | Path) -> dict[str, object]:
    audio_path = Path(path)
    info = sf.info(audio_path)
    return {
        "file": str(audio_path),
        "durationSeconds": round_float(info.duration),
        "sampleRate": int(info.samplerate),
        "channels": int(info.channels),
        "frames": int(info.frames),
    }


def parse_window(value: str | None) -> TimeWindow | None:
    if value is None:
        return None
    if ":" not in value:
        raise ValueError("window must be formatted as start:end")
    start_text, end_text = value.split(":", 1)
    start = float(start_text) if start_text else 0.0
    end = float(end_text) if end_text else None
    if start < 0:
        raise ValueError("window start must be >= 0")
    if end is not None and end < start:
        raise ValueError("window end must be >= window start")
    return TimeWindow(start=start, end=end)


def slice_window(audio: AudioData, window: TimeWindow | None) -> tuple[np.ndarray, TimeWindow]:
    duration = audio.duration_seconds
    if window is None:
        window = TimeWindow(0.0, duration)

    start = min(max(window.start, 0.0), duration)
    end = min(max(window.resolved_end(duration), start), duration)
    start_frame = int(round(start * audio.sample_rate))
    end_frame = int(round(end * audio.sample_rate))
    return audio.samples[start_frame:end_frame, :], TimeWindow(start, end)


def parse_bands(value: str) -> list[tuple[float, float]]:
    bands: list[tuple[float, float]] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"band must be formatted as low:high: {item}")
        low_text, high_text = item.split(":", 1)
        low = float(low_text)
        high = float(high_text)
        if low < 0 or high <= low:
            raise ValueError(f"invalid band range: {item}")
        bands.append((low, high))
    if not bands:
        raise ValueError("at least one band is required")
    return bands
