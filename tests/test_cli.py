from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf


def run_probe(*args: str) -> tuple[int, dict]:
    command = [sys.executable, "-m", "audio_probe", *args]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    payload = json.loads(completed.stdout) if completed.stdout else {}
    return completed.returncode, payload


def write_wav(path: Path, samples: np.ndarray, sample_rate: int = 48_000) -> None:
    sf.write(path, samples, sample_rate, subtype="PCM_24")


def test_info_reports_shape(tmp_path: Path) -> None:
    path = tmp_path / "sine.wav"
    samples = 0.5 * np.sin(2.0 * np.pi * 1000.0 * np.arange(48_000) / 48_000)
    write_wav(path, samples)

    code, payload = run_probe("info", str(path), "--json")

    assert code == 0
    assert payload["sampleRate"] == 48_000
    assert payload["channels"] == 1
    assert payload["frames"] == 48_000
    assert payload["durationSeconds"] == 1.0


def test_metrics_reports_sine_rms_and_peak(tmp_path: Path) -> None:
    path = tmp_path / "sine.wav"
    samples = 0.5 * np.sin(2.0 * np.pi * 1000.0 * np.arange(48_000) / 48_000)
    write_wav(path, samples)

    code, payload = run_probe("metrics", str(path), "--window", "0:1", "--json")

    assert code == 0
    assert math.isclose(payload["rmsDb"], -9.0309, abs_tol=0.02)
    assert math.isclose(payload["peakDb"], -6.0206, abs_tol=0.02)
    assert payload["clippingSamples"] == 0


def test_bands_identifies_sine_band(tmp_path: Path) -> None:
    path = tmp_path / "sine.wav"
    samples = 0.5 * np.sin(2.0 * np.pi * 1000.0 * np.arange(48_000) / 48_000)
    write_wav(path, samples)

    code, payload = run_probe(
        "bands",
        str(path),
        "--bands",
        "20:200,200:2000,2000:16000",
        "--json",
    )

    assert code == 0
    low, mid, high = payload["bands"]
    assert mid["rmsDb"] > low["rmsDb"] + 40
    assert mid["rmsDb"] > high["rmsDb"] + 40


def test_stereo_balance_is_positive_for_left_heavy(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    t = np.arange(48_000) / 48_000
    left = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    right = 0.1 * np.sin(2.0 * np.pi * 440.0 * t)
    write_wav(path, np.column_stack([left, right]))

    code, payload = run_probe("stereo", str(path), "--json")

    assert code == 0
    assert payload["balance"] > 0.6


def test_compare_reports_after_minus_before_delta(tmp_path: Path) -> None:
    before = tmp_path / "before.wav"
    after = tmp_path / "after.wav"
    t = np.arange(48_000) / 48_000
    write_wav(before, 0.5 * np.sin(2.0 * np.pi * 440.0 * t))
    write_wav(after, 0.25 * np.sin(2.0 * np.pi * 440.0 * t))

    code, payload = run_probe("compare", str(before), str(after), "--json")

    assert code == 0
    assert math.isclose(payload["rmsDeltaDb"], -6.0206, abs_tol=0.03)
    assert math.isclose(payload["peakDeltaDb"], -6.0206, abs_tol=0.03)


def test_check_returns_nonzero_for_failure(tmp_path: Path) -> None:
    audio = tmp_path / "sine.wav"
    checks = tmp_path / "checks.json"
    samples = 0.5 * np.sin(2.0 * np.pi * 1000.0 * np.arange(48_000) / 48_000)
    write_wav(audio, samples)
    checks.write_text(
        json.dumps(
            [
                {
                    "file": str(audio),
                    "metric": "rmsDb",
                    "window": "0:1",
                    "op": "<",
                    "value": -60,
                }
            ]
        ),
        encoding="utf-8",
    )

    code, payload = run_probe("check", str(checks), "--json")

    assert code == 1
    assert payload["passed"] is False
