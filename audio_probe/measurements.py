from __future__ import annotations

import math
import operator
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal

from .audio import TimeWindow, load_audio, parse_bands, parse_window, round_float, slice_window

DB_FLOOR = -300.0
EPSILON = 1e-15
DEFAULT_BANDS = "20:200,200:2000,2000:16000"


def dbfs(value: float) -> float:
    if not math.isfinite(value) or value <= EPSILON:
        return DB_FLOOR
    return round_float(20.0 * math.log10(value))


def rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def peak(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.max(np.abs(samples)))


def _mono(samples: np.ndarray) -> np.ndarray:
    if samples.size == 0:
        return np.array([], dtype=np.float64)
    if samples.ndim == 1:
        return samples
    if samples.shape[1] == 1:
        return samples[:, 0]
    return np.mean(samples, axis=1)


def _window_json(window: TimeWindow) -> dict[str, float]:
    return {"start": round_float(window.start), "end": round_float(window.end or window.start)}


def measure_metrics(path: str | Path, window: TimeWindow | None = None) -> dict[str, Any]:
    audio = load_audio(path)
    samples, actual_window = slice_window(audio, window)
    mono = _mono(samples)
    rms_value = rms(samples)
    peak_value = peak(samples)
    rms_db = dbfs(rms_value)
    peak_db = dbfs(peak_value)
    envelope = envelope_values(mono, audio.sample_rate, window_ms=50.0, hop_ms=50.0)

    silences = silence_ranges(envelope, actual_window.start)
    onsets = onset_times(envelope, actual_window.start)
    return {
        "file": str(path),
        "window": _window_json(actual_window),
        "rmsDb": rms_db,
        "peakDb": peak_db,
        "crestFactorDb": round_float(peak_db - rms_db) if rms_value > EPSILON else 0.0,
        "clippingSamples": int(np.count_nonzero(np.abs(samples) >= 0.999969482421875)),
        "dcOffset": round_float(float(np.mean(samples)) if samples.size else 0.0),
        "spectralCentroidHz": spectral_centroid_hz(mono, audio.sample_rate),
        "silenceRanges": silences,
        "silenceDurationSeconds": round_float(
            sum(item["end"] - item["start"] for item in silences)
        ),
        "onsetTimes": onsets,
        "onsetCount": len(onsets),
        "decaySlopeDbPerSecond": decay_slope_db_per_second(envelope),
    }


def measure_bands(
    path: str | Path,
    bands: list[tuple[float, float]],
    window: TimeWindow | None = None,
) -> dict[str, Any]:
    audio = load_audio(path)
    samples, actual_window = slice_window(audio, window)
    mono = _mono(samples)
    return {
        "file": str(path),
        "window": _window_json(actual_window),
        "bands": [
            {
                "rangeHz": [round_float(low), round_float(high)],
                "rmsDb": band_rms_db(mono, audio.sample_rate, low, high),
            }
            for low, high in bands
        ],
    }


def band_rms_db(samples: np.ndarray, sample_rate: int, low_hz: float, high_hz: float) -> float:
    if samples.size == 0:
        return DB_FLOOR
    nyquist = sample_rate / 2.0
    low = max(0.0, low_hz)
    high = min(high_hz, nyquist)
    if high <= low:
        return DB_FLOOR

    spectrum = np.fft.rfft(samples)
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask):
        return DB_FLOOR

    power = np.square(np.abs(spectrum[mask]))
    selected_freqs = freqs[mask]
    weights = np.ones_like(power)
    weights[(selected_freqs > 0.0) & (selected_freqs < nyquist)] = 2.0
    mean_square = float(np.sum(power * weights) / (samples.size * samples.size))
    return dbfs(math.sqrt(max(mean_square, 0.0)))


def measure_envelope(path: str | Path, window_ms: float, hop_ms: float) -> dict[str, Any]:
    audio = load_audio(path)
    frames = envelope_values(audio.mono, audio.sample_rate, window_ms=window_ms, hop_ms=hop_ms)
    rms_values = [frame["rmsDb"] for frame in frames]
    max_step = max((abs(b - a) for a, b in zip(rms_values, rms_values[1:])), default=0.0)
    return {
        "file": str(path),
        "windowMs": round_float(window_ms),
        "hopMs": round_float(hop_ms),
        "frames": frames,
        "maxEnvelopeStepDb": round_float(max_step),
    }


def envelope_values(
    samples: np.ndarray,
    sample_rate: int,
    *,
    window_ms: float,
    hop_ms: float,
) -> list[dict[str, float]]:
    if window_ms <= 0 or hop_ms <= 0:
        raise ValueError("window-ms and hop-ms must be > 0")
    window_size = max(1, int(round(sample_rate * window_ms / 1000.0)))
    hop_size = max(1, int(round(sample_rate * hop_ms / 1000.0)))
    if samples.size == 0:
        return [{"time": 0.0, "rmsDb": DB_FLOOR, "peakDb": DB_FLOOR}]

    frames: list[dict[str, float]] = []
    last_start = max(samples.size - window_size, 0)
    starts = range(0, samples.size, hop_size)
    for start in starts:
        if start > last_start and frames:
            break
        frame = samples[start : start + window_size]
        if frame.size == 0:
            continue
        frames.append(
            {
                "time": round_float(start / sample_rate),
                "rmsDb": dbfs(rms(frame)),
                "peakDb": dbfs(peak(frame)),
            }
        )
    return frames


def measure_stereo(path: str | Path, window: TimeWindow | None = None) -> dict[str, Any]:
    audio = load_audio(path)
    samples, actual_window = slice_window(audio, window)
    if samples.size == 0:
        left = right = np.array([], dtype=np.float64)
    elif samples.shape[1] == 1:
        left = right = samples[:, 0]
    else:
        left = samples[:, 0]
        right = samples[:, 1]

    left_rms = rms(left)
    right_rms = rms(right)
    denominator = left_rms + right_rms
    balance = (left_rms - right_rms) / denominator if denominator > EPSILON else 0.0
    return {
        "file": str(path),
        "window": _window_json(actual_window),
        "leftRmsDb": dbfs(left_rms),
        "rightRmsDb": dbfs(right_rms),
        "balance": round_float(balance),
        "stereoBalance": round_float(balance),
    }


def measure_compare(
    before_path: str | Path,
    after_path: str | Path,
    window: TimeWindow | None = None,
    bands: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    bands = parse_bands(DEFAULT_BANDS) if bands is None else bands
    before_metrics = measure_metrics(before_path, window)
    after_metrics = measure_metrics(after_path, window)
    before_bands = measure_bands(before_path, bands, window)["bands"]
    after_bands = measure_bands(after_path, bands, window)["bands"]
    return {
        "beforeFile": str(before_path),
        "afterFile": str(after_path),
        "window": after_metrics["window"],
        "rmsDeltaDb": round_float(after_metrics["rmsDb"] - before_metrics["rmsDb"]),
        "peakDeltaDb": round_float(after_metrics["peakDb"] - before_metrics["peakDb"]),
        "bandDeltas": [
            {
                "rangeHz": after_band["rangeHz"],
                "rmsDeltaDb": round_float(after_band["rmsDb"] - before_band["rmsDb"]),
            }
            for before_band, after_band in zip(before_bands, after_bands, strict=True)
        ],
    }


def measure_transients(path: str | Path, window: TimeWindow | None = None) -> dict[str, Any]:
    audio = load_audio(path)
    samples, actual_window = slice_window(audio, window)
    mono = _mono(samples)
    jumps = np.abs(np.diff(mono)) if mono.size >= 2 else np.array([0.0])
    max_jump = float(np.max(jumps)) if jumps.size else 0.0
    high_start = min(6000.0, audio.sample_rate / 2.0)
    high_db = band_rms_db(mono, audio.sample_rate, high_start, audio.sample_rate / 2.0)
    peak_value = peak(mono)
    click_score = min(1.0, max_jump / peak_value) if peak_value > EPSILON else 0.0
    transient_times = transient_times_from_jumps(jumps, audio.sample_rate, actual_window.start, peak_value)
    return {
        "file": str(path),
        "window": _window_json(actual_window),
        "maxSampleJump": round_float(max_jump),
        "maxSampleJumpDb": dbfs(max_jump),
        "highFrequencyBurstDb": high_db,
        "clickScore": round_float(click_score),
        "transientCount": len(transient_times),
        "transientTimes": transient_times,
    }


def transient_times_from_jumps(
    jumps: np.ndarray,
    sample_rate: int,
    offset_seconds: float,
    peak_value: float,
    *,
    min_jump: float = 0.15,
    relative_jump: float = 0.55,
) -> list[float]:
    if jumps.size == 0 or sample_rate <= 0:
        return []
    threshold = max(min_jump, peak_value * relative_jump)
    candidates = np.flatnonzero(jumps >= threshold)
    if candidates.size == 0:
        return []

    refractory = max(1, int(round(sample_rate * 0.01)))
    times: list[float] = []
    last_index = -refractory
    for index in candidates:
        if int(index) - last_index < refractory:
            continue
        times.append(round_float(offset_seconds + (int(index) + 1) / sample_rate))
        last_index = int(index)
    return times


def spectral_centroid_hz(samples: np.ndarray, sample_rate: int) -> float:
    if samples.size == 0:
        return 0.0
    magnitudes = np.abs(np.fft.rfft(samples))
    total = float(np.sum(magnitudes))
    if total <= EPSILON:
        return 0.0
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    return round_float(float(np.sum(freqs * magnitudes) / total))


def silence_ranges(
    envelope: list[dict[str, float]], offset_seconds: float, threshold_db: float = -60.0
) -> list[dict[str, float]]:
    ranges: list[dict[str, float]] = []
    current_start: float | None = None
    last_time = offset_seconds
    step = envelope[1]["time"] - envelope[0]["time"] if len(envelope) > 1 else 0.0
    for frame in envelope:
        time = offset_seconds + frame["time"]
        last_time = time + step
        if frame["rmsDb"] <= threshold_db and current_start is None:
            current_start = time
        elif frame["rmsDb"] > threshold_db and current_start is not None:
            ranges.append({"start": round_float(current_start), "end": round_float(time)})
            current_start = None
    if current_start is not None:
        ranges.append({"start": round_float(current_start), "end": round_float(last_time)})
    return ranges


def onset_times(
    envelope: list[dict[str, float]],
    offset_seconds: float,
    *,
    min_level_db: float = -50.0,
    min_step_db: float = 6.0,
) -> list[float]:
    times: list[float] = []
    previous = envelope[0]["rmsDb"] if envelope else DB_FLOOR
    for frame in envelope[1:]:
        current = frame["rmsDb"]
        if current >= min_level_db and current - previous >= min_step_db:
            times.append(round_float(offset_seconds + frame["time"]))
        previous = current
    return times


def decay_slope_db_per_second(envelope: list[dict[str, float]]) -> float:
    if len(envelope) < 2:
        return 0.0
    values = np.array([frame["rmsDb"] for frame in envelope], dtype=np.float64)
    times = np.array([frame["time"] for frame in envelope], dtype=np.float64)
    finite = values > DB_FLOOR
    if np.count_nonzero(finite) < 2:
        return 0.0
    peak_index = int(np.argmax(values))
    tail = np.arange(values.size) >= peak_index
    mask = finite & tail
    if np.count_nonzero(mask) < 2:
        return 0.0
    slope, _ = np.polyfit(times[mask], values[mask], 1)
    return round_float(float(slope))


def write_plot(path: str | Path, out_path: str | Path) -> dict[str, Any]:
    cache_root = Path(tempfile.gettempdir()) / "audio-probe-matplotlib"
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "mplconfig"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root / "xdg-cache"))

    import matplotlib.pyplot as plt

    audio = load_audio(path)
    mono = audio.mono
    times = np.arange(mono.size) / audio.sample_rate
    envelope = envelope_values(mono, audio.sample_rate, window_ms=50.0, hop_ms=10.0)

    fig, axes = plt.subplots(3, 1, figsize=(12, 8), constrained_layout=True)
    axes[0].plot(times, mono, linewidth=0.8)
    axes[0].set_title("Waveform")
    axes[0].set_xlabel("Time (s)")
    axes[0].set_ylabel("Amplitude")

    axes[1].plot([frame["time"] for frame in envelope], [frame["rmsDb"] for frame in envelope])
    axes[1].set_title("Envelope")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("RMS (dBFS)")
    axes[1].set_ylim(bottom=max(DB_FLOOR, -120))

    axes[2].specgram(mono, NFFT=2048, Fs=audio.sample_rate, noverlap=1536)
    axes[2].set_title("Spectrogram")
    axes[2].set_xlabel("Time (s)")
    axes[2].set_ylabel("Frequency (Hz)")

    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return {"file": str(path), "out": str(out_path)}


def evaluate_check(check: dict[str, Any]) -> dict[str, Any]:
    op = check["op"]
    expected = check["value"]

    if op in {"delta<", "delta>"}:
        before_file = check.get("beforeFile") or check.get("before") or check.get("file")
        after_file = check.get("afterFile") or check.get("after") or check.get("compareFile")
        if not before_file or not after_file:
            raise ValueError("delta checks require beforeFile and afterFile")
        before = resolve_metric(before_file, check["metric"], check.get("window"))
        after = resolve_metric(after_file, check["metric"], check.get("window"))
        actual = round_float(after - before)
    else:
        actual = resolve_metric(check["file"], check["metric"], check.get("window"))

    passed = compare_values(float(actual), op, expected)
    return {
        "check": check,
        "actual": actual,
        "passed": passed,
    }


def resolve_metric(path: str | Path, metric_path: str, window_value: str | None = None) -> float:
    window = parse_window(window_value)
    if metric_path.startswith("bands."):
        parts = metric_path.split(".")
        if len(parts) != 3 or parts[2] != "rmsDb":
            raise ValueError(f"unsupported band metric path: {metric_path}")
        bands = parse_bands(parts[1])
        return float(measure_bands(path, bands, window)["bands"][0]["rmsDb"])

    if metric_path in {"leftRmsDb", "rightRmsDb", "balance", "stereoBalance"}:
        return float(measure_stereo(path, window)[metric_path])

    if metric_path in {"maxSampleJump", "maxSampleJumpDb", "highFrequencyBurstDb", "clickScore"}:
        return float(measure_transients(path, window)[metric_path])

    metrics = measure_metrics(path, window)
    if metric_path not in metrics:
        raise ValueError(f"unsupported metric path: {metric_path}")
    return float(metrics[metric_path])


def compare_values(actual: float, op: str, expected: Any) -> bool:
    operations: dict[str, Callable[[float, float], bool]] = {
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
        "==": operator.eq,
        "delta<": operator.lt,
        "delta>": operator.gt,
    }
    if op == "between":
        low, high = expected
        return float(low) <= actual <= float(high)
    if op not in operations:
        raise ValueError(f"unsupported operator: {op}")
    return operations[op](actual, float(expected))


def highpass_filter(samples: np.ndarray, sample_rate: int, cutoff_hz: float) -> np.ndarray:
    if samples.size == 0:
        return samples
    sos = signal.butter(4, cutoff_hz, btype="highpass", fs=sample_rate, output="sos")
    return signal.sosfilt(sos, samples)
