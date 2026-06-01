from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal

from .audio import TimeWindow, file_info, load_audio, round_float, slice_window
from .measurements import DB_FLOOR, EPSILON, dbfs, envelope_values, peak, rms


def _mono(samples: np.ndarray) -> np.ndarray:
    if samples.size == 0:
        return np.array([], dtype=np.float64)
    if samples.shape[1] == 1:
        return samples[:, 0]
    return np.mean(samples, axis=1)


def _window_json(window: TimeWindow) -> dict[str, float]:
    return {"start": round_float(window.start), "end": round_float(window.end or window.start)}


def _k_weighted(samples: np.ndarray) -> np.ndarray:
    """Approximate BS.1770 K-weighting for common 48 kHz render/test assets."""
    if samples.size == 0:
        return samples
    high_shelf_b = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285])
    high_shelf_a = np.array([1.0, -1.69065929318241, 0.73248077421585])
    high_pass_b = np.array([1.0, -2.0, 1.0])
    high_pass_a = np.array([1.0, -1.99004745483398, 0.99007225036621])
    filtered = signal.lfilter(high_shelf_b, high_shelf_a, samples, axis=0)
    return signal.lfilter(high_pass_b, high_pass_a, filtered, axis=0)


def _lufs_from_power(power: float) -> float:
    if not math.isfinite(power) or power <= EPSILON:
        return DB_FLOOR
    return round_float(-0.691 + 10.0 * math.log10(power))


def _block_loudness(samples: np.ndarray, sample_rate: int, seconds: float) -> list[float]:
    block = max(1, int(round(sample_rate * seconds)))
    hop = max(1, int(round(block * 0.25)))
    if samples.shape[0] < block:
        if samples.shape[0] == 0:
            return []
        power = float(np.mean(np.square(samples)))
        return [_lufs_from_power(power)]

    values: list[float] = []
    for start in range(0, samples.shape[0] - block + 1, hop):
        frame = samples[start : start + block, :]
        values.append(_lufs_from_power(float(np.mean(np.square(frame)))))
    return values


def measure_loudness(path: str | Path, window: TimeWindow | None = None) -> dict[str, Any]:
    audio = load_audio(path)
    samples, actual_window = slice_window(audio, window)
    loudness_samples, loudness_rate = _resample_for_loudness(samples, audio.sample_rate)
    weighted = _k_weighted(loudness_samples)
    momentary = _block_loudness(weighted, loudness_rate, 0.4)
    short_term = _block_loudness(weighted, loudness_rate, 3.0)

    gated = [value for value in momentary if value > -70.0]
    if gated:
        relative_gate = _lufs_from_power(float(np.mean([10.0 ** ((value + 0.691) / 10.0) for value in gated]))) - 10.0
        gated = [value for value in gated if value > relative_gate]
    integrated_power = (
        float(np.mean([10.0 ** ((value + 0.691) / 10.0) for value in gated])) if gated else 0.0
    )
    integrated = _lufs_from_power(integrated_power)

    short_gated = [value for value in short_term if value > -70.0 and value > integrated - 20.0]
    loudness_range = (
        round_float(float(np.percentile(short_gated, 95) - np.percentile(short_gated, 10)))
        if len(short_gated) >= 2
        else 0.0
    )

    true_peak = _true_peak(samples)
    return {
        "file": str(path),
        "window": _window_json(actual_window),
        "lufsIntegrated": integrated,
        "lufsMomentaryMax": max(momentary, default=DB_FLOOR),
        "lufsShortTermMax": max(short_term, default=DB_FLOOR),
        "loudnessRangeLufs": loudness_range,
        "truePeakDb": dbfs(true_peak),
        "truePeak": round_float(true_peak),
    }


def _resample_for_loudness(samples: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
    if samples.size == 0 or sample_rate == 48_000:
        return samples, sample_rate
    gcd = math.gcd(sample_rate, 48_000)
    return signal.resample_poly(samples, 48_000 // gcd, sample_rate // gcd, axis=0), 48_000


def _true_peak(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    oversampled = signal.resample_poly(samples, 4, 1, axis=0)
    return peak(oversampled)


def measure_phase(path: str | Path, window: TimeWindow | None = None) -> dict[str, Any]:
    audio = load_audio(path)
    samples, actual_window = slice_window(audio, window)
    mono = _mono(samples)
    if samples.size == 0:
        left = right = mono
    elif samples.shape[1] == 1:
        left = right = samples[:, 0]
    else:
        left = samples[:, 0]
        right = samples[:, 1]

    left_centered = left - float(np.mean(left)) if left.size else left
    right_centered = right - float(np.mean(right)) if right.size else right
    denominator = float(np.linalg.norm(left_centered) * np.linalg.norm(right_centered))
    correlation = float(np.dot(left_centered, right_centered) / denominator) if denominator > EPSILON else 1.0
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    mid_rms = rms(mid)
    side_rms = rms(side)
    width = side_rms / mid_rms if mid_rms > EPSILON else 0.0
    mono_rms = rms(mono)
    stereo_rms = rms(samples)
    return {
        "file": str(path),
        "window": _window_json(actual_window),
        "phaseCorrelation": round_float(max(-1.0, min(1.0, correlation))),
        "stereoWidth": round_float(width),
        "monoRmsDb": dbfs(mono_rms),
        "monoDeltaDb": round_float(dbfs(mono_rms) - dbfs(stereo_rms)) if stereo_rms > EPSILON else 0.0,
        "monoCompatible": correlation >= 0.0,
    }


def measure_diff(
    before_path: str | Path,
    after_path: str | Path,
    window: TimeWindow | None = None,
    *,
    align: bool = True,
    max_lag_ms: float = 100.0,
) -> dict[str, Any]:
    before_audio = load_audio(before_path)
    after_audio = load_audio(after_path)
    before_samples, actual_window = slice_window(before_audio, window)
    after_samples, _ = slice_window(after_audio, window)
    sample_rate = before_audio.sample_rate
    sample_offset = _best_offset(_mono(before_samples), _mono(after_samples), sample_rate, max_lag_ms) if align else 0
    before_aligned, after_aligned = _align_samples(before_samples, after_samples, sample_offset)
    channels = min(before_aligned.shape[1], after_aligned.shape[1]) if before_aligned.size and after_aligned.size else 0
    before_aligned = before_aligned[:, :channels]
    after_aligned = after_aligned[:, :channels]
    residual = after_aligned - before_aligned if channels else np.empty((0, 0), dtype=np.float64)
    before_rms = rms(before_aligned)
    residual_rms = rms(residual)
    return {
        "beforeFile": str(before_path),
        "afterFile": str(after_path),
        "window": _window_json(actual_window),
        "sampleOffset": int(sample_offset),
        "timeOffsetSeconds": round_float(sample_offset / sample_rate if sample_rate else 0.0),
        "comparedFrames": int(residual.shape[0]),
        "durationDeltaSeconds": round_float(after_audio.duration_seconds - before_audio.duration_seconds),
        "residualRmsDb": dbfs(residual_rms),
        "residualPeakDb": dbfs(peak(residual)),
        "beforeRmsDb": dbfs(before_rms),
        "afterRmsDb": dbfs(rms(after_aligned)),
        "residualToBeforeDb": round_float(dbfs(residual_rms) - dbfs(before_rms))
        if before_rms > EPSILON
        else 0.0,
    }


def _best_offset(before: np.ndarray, after: np.ndarray, sample_rate: int, max_lag_ms: float) -> int:
    if before.size == 0 or after.size == 0:
        return 0
    limit = min(before.size, after.size, max(1, int(round(sample_rate * max_lag_ms / 1000.0))))
    before_probe = before[: min(before.size, sample_rate * 30)]
    after_probe = after[: min(after.size, before_probe.size + limit)]
    correlation = signal.correlate(after_probe, before_probe, mode="full")
    lags = signal.correlation_lags(after_probe.size, before_probe.size, mode="full")
    mask = np.abs(lags) <= limit
    if not np.any(mask):
        return 0
    return int(lags[mask][int(np.argmax(correlation[mask]))])


def _align_samples(before: np.ndarray, after: np.ndarray, offset: int) -> tuple[np.ndarray, np.ndarray]:
    if offset > 0:
        after = after[offset:, :]
    elif offset < 0:
        before = before[-offset:, :]
    length = min(before.shape[0], after.shape[0])
    return before[:length, :], after[:length, :]


def measure_shape(
    path: str | Path,
    compare_path: str | Path | None = None,
    *,
    silence_threshold_db: float = -60.0,
) -> dict[str, Any]:
    primary = _shape_for_file(path, silence_threshold_db)
    if compare_path is None:
        return primary
    other = _shape_for_file(compare_path, silence_threshold_db)
    return {
        "file": str(path),
        "compareFile": str(compare_path),
        "reference": primary,
        "candidate": other,
        "durationDeltaSeconds": round_float(other["durationSeconds"] - primary["durationSeconds"]),
        "framesDelta": int(other["frames"] - primary["frames"]),
        "sampleRateMatches": primary["sampleRate"] == other["sampleRate"],
        "channelsMatch": primary["channels"] == other["channels"],
    }


def _shape_for_file(path: str | Path, silence_threshold_db: float) -> dict[str, Any]:
    audio = load_audio(path)
    info = file_info(path)
    envelope = envelope_values(audio.mono, audio.sample_rate, window_ms=50.0, hop_ms=10.0)
    active = [frame for frame in envelope if frame["rmsDb"] > silence_threshold_db]
    if active:
        leading = active[0]["time"]
        trailing = max(0.0, audio.duration_seconds - active[-1]["time"])
    else:
        leading = audio.duration_seconds
        trailing = audio.duration_seconds
    return {
        **info,
        "silenceThresholdDb": round_float(silence_threshold_db),
        "leadingSilenceSeconds": round_float(leading),
        "trailingSilenceSeconds": round_float(trailing),
        "activeDurationSeconds": round_float(max(0.0, audio.duration_seconds - leading - trailing)),
    }
