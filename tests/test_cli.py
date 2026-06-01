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


def run_text(*args: str) -> tuple[int, str, str]:
    command = [sys.executable, "-m", "audio_probe", *args]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr


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


def test_invalid_windows_return_usage_error(tmp_path: Path) -> None:
    path = tmp_path / "sine.wav"
    samples = 0.5 * np.sin(2.0 * np.pi * 1000.0 * np.arange(48_000) / 48_000)
    write_wav(path, samples)

    for window in ("0.5", "-1:1", "2:1"):
        code, stdout, stderr = run_text("metrics", str(path), f"--window={window}", "--json")

        assert code == 2
        assert stdout == ""
        assert "error:" in stderr


def test_out_of_range_window_returns_silence_floor(tmp_path: Path) -> None:
    path = tmp_path / "sine.wav"
    samples = 0.5 * np.sin(2.0 * np.pi * 1000.0 * np.arange(48_000) / 48_000)
    write_wav(path, samples)

    code, payload = run_probe("metrics", str(path), "--window", "5:6", "--json")

    assert code == 0
    assert payload["window"] == {"start": 1.0, "end": 1.0}
    assert payload["rmsDb"] == -300.0
    assert payload["onsetCount"] == 0


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


def test_bands_reject_invalid_ranges(tmp_path: Path) -> None:
    path = tmp_path / "sine.wav"
    write_wav(path, np.zeros(48_000))

    for bands in ("200", "200:20", "-1:20", ","):
        code, stdout, stderr = run_text("bands", str(path), f"--bands={bands}", "--json")

        assert code == 2
        assert stdout == ""
        assert "error:" in stderr


def test_band_above_nyquist_reports_floor(tmp_path: Path) -> None:
    path = tmp_path / "sine.wav"
    write_wav(path, np.zeros(48_000))

    code, payload = run_probe("bands", str(path), "--bands", "30000:40000", "--json")

    assert code == 0
    assert payload["bands"][0]["rmsDb"] == -300.0


def test_stereo_balance_is_positive_for_left_heavy(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    t = np.arange(48_000) / 48_000
    left = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    right = 0.1 * np.sin(2.0 * np.pi * 440.0 * t)
    write_wav(path, np.column_stack([left, right]))

    code, payload = run_probe("stereo", str(path), "--json")

    assert code == 0
    assert payload["balance"] > 0.6


def test_stereo_uses_first_two_channels_for_multichannel(tmp_path: Path) -> None:
    path = tmp_path / "multichannel.wav"
    t = np.arange(48_000) / 48_000
    left = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    right = 0.1 * np.sin(2.0 * np.pi * 440.0 * t)
    ignored = 0.9 * np.sin(2.0 * np.pi * 440.0 * t)
    write_wav(path, np.column_stack([left, right, ignored]))

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


def test_diff_reports_low_residual_for_identical_files(tmp_path: Path) -> None:
    before = tmp_path / "before.wav"
    after = tmp_path / "after.wav"
    t = np.arange(48_000) / 48_000
    samples = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    write_wav(before, samples)
    write_wav(after, samples)

    code, payload = run_probe("diff", str(before), str(after), "--json")

    assert code == 0
    assert payload["sampleOffset"] == 0
    assert payload["residualRmsDb"] <= -250


def test_diff_alignment_and_no_align_modes(tmp_path: Path) -> None:
    before = tmp_path / "before.wav"
    after = tmp_path / "after.wav"
    t = np.arange(48_000) / 48_000
    samples = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    shifted = np.concatenate([np.zeros(240), samples[:-240]])
    write_wav(before, samples)
    write_wav(after, shifted)

    aligned_code, aligned = run_probe("diff", str(before), str(after), "--json")
    raw_code, raw = run_probe("diff", str(before), str(after), "--no-align", "--json")

    assert aligned_code == 0
    assert raw_code == 0
    assert aligned["sampleOffset"] != 0
    assert aligned["residualRmsDb"] < raw["residualRmsDb"] - 20


def test_loudness_reports_true_peak(tmp_path: Path) -> None:
    path = tmp_path / "sine.wav"
    samples = 0.5 * np.sin(2.0 * np.pi * 1000.0 * np.arange(48_000) / 48_000)
    write_wav(path, samples)

    code, payload = run_probe("loudness", str(path), "--json")

    assert code == 0
    assert math.isclose(payload["truePeakDb"], -6.0206, abs_tol=0.1)
    assert payload["lufsIntegrated"] < 0


def test_loudness_handles_silence_short_files_and_non_48k(tmp_path: Path) -> None:
    silence = tmp_path / "silence.wav"
    short = tmp_path / "short.wav"
    low_rate = tmp_path / "low-rate.wav"
    write_wav(silence, np.zeros(48_000))
    write_wav(short, np.zeros(2_000))
    t = np.arange(44_100) / 44_100
    write_wav(low_rate, 0.5 * np.sin(2.0 * np.pi * 1000.0 * t), sample_rate=44_100)

    silence_code, silence_payload = run_probe("loudness", str(silence), "--json")
    short_code, short_payload = run_probe("loudness", str(short), "--json")
    low_rate_code, low_rate_payload = run_probe("loudness", str(low_rate), "--json")

    assert silence_code == 0
    assert silence_payload["lufsIntegrated"] == -300.0
    assert silence_payload["truePeakDb"] == -300.0
    assert short_code == 0
    assert short_payload["loudnessRangeLufs"] == 0.0
    assert low_rate_code == 0
    assert math.isfinite(low_rate_payload["lufsIntegrated"])


def test_phase_flags_inverted_stereo(tmp_path: Path) -> None:
    path = tmp_path / "inverted.wav"
    t = np.arange(48_000) / 48_000
    left = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    right = -left
    write_wav(path, np.column_stack([left, right]))

    code, payload = run_probe("phase", str(path), "--json")

    assert code == 0
    assert payload["phaseCorrelation"] < -0.99
    assert payload["monoCompatible"] is False


def test_phase_handles_centered_mono_and_silent_files(tmp_path: Path) -> None:
    mono = tmp_path / "mono.wav"
    centered = tmp_path / "centered.wav"
    silent = tmp_path / "silent.wav"
    t = np.arange(48_000) / 48_000
    samples = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    write_wav(mono, samples)
    write_wav(centered, np.column_stack([samples, samples]))
    write_wav(silent, np.zeros((48_000, 2)))

    mono_code, mono_payload = run_probe("phase", str(mono), "--json")
    centered_code, centered_payload = run_probe("phase", str(centered), "--json")
    silent_code, silent_payload = run_probe("phase", str(silent), "--json")

    assert mono_code == 0
    assert mono_payload["phaseCorrelation"] == 1.0
    assert centered_code == 0
    assert centered_payload["stereoWidth"] == 0.0
    assert silent_code == 0
    assert silent_payload["monoCompatible"] is True


def test_shape_reports_silence_and_format_delta(tmp_path: Path) -> None:
    before = tmp_path / "before.wav"
    after = tmp_path / "after.wav"
    samples = np.zeros(48_000)
    samples[12_000:36_000] = 0.5 * np.sin(2.0 * np.pi * 440.0 * np.arange(24_000) / 48_000)
    write_wav(before, samples)
    write_wav(after, np.concatenate([samples, np.zeros(4_800)]))

    code, payload = run_probe("shape", str(before), str(after), "--json")

    assert code == 0
    assert payload["sampleRateMatches"] is True
    assert payload["durationDeltaSeconds"] == 0.1
    assert payload["reference"]["leadingSilenceSeconds"] >= 0.2
    assert payload["reference"]["trailingSilenceSeconds"] >= 0.2


def test_shape_single_file_and_mismatch_flags(tmp_path: Path) -> None:
    reference = tmp_path / "reference.wav"
    candidate = tmp_path / "candidate.wav"
    write_wav(reference, np.zeros((48_000, 1)))
    write_wav(candidate, np.zeros((22_050, 2)), sample_rate=44_100)

    single_code, single = run_probe("shape", str(reference), "--json")
    compare_code, compare = run_probe("shape", str(reference), str(candidate), "--json")

    assert single_code == 0
    assert "reference" not in single
    assert single["durationSeconds"] == 1.0
    assert compare_code == 0
    assert compare["sampleRateMatches"] is False
    assert compare["channelsMatch"] is False


def test_transients_reports_count_and_times(tmp_path: Path) -> None:
    path = tmp_path / "clicks.wav"
    samples = np.zeros(48_000)
    samples[4_800:4_802] = [0.9, -0.9]
    samples[24_000:24_002] = [0.9, -0.9]
    write_wav(path, samples)

    code, payload = run_probe("transients", str(path), "--json")

    assert code == 0
    assert payload["transientCount"] == 2
    assert payload["transientTimes"] == [0.1, 0.5]


def test_transients_handles_quiet_and_refractory_cases(tmp_path: Path) -> None:
    quiet = tmp_path / "quiet.wav"
    clustered = tmp_path / "clustered.wav"
    write_wav(quiet, np.zeros(48_000))
    samples = np.zeros(48_000)
    samples[4_800:4_802] = [0.9, -0.9]
    samples[4_820:4_822] = [0.9, -0.9]
    write_wav(clustered, samples)

    quiet_code, quiet_payload = run_probe("transients", str(quiet), "--json")
    clustered_code, clustered_payload = run_probe("transients", str(clustered), "--json")

    assert quiet_code == 0
    assert quiet_payload["transientCount"] == 0
    assert clustered_code == 0
    assert clustered_payload["transientCount"] == 1


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


def test_check_supports_nested_compare_band_metric(tmp_path: Path) -> None:
    before = tmp_path / "before.wav"
    after = tmp_path / "after.wav"
    checks = tmp_path / "checks.json"
    t = np.arange(48_000) / 48_000
    write_wav(before, 0.5 * np.sin(2.0 * np.pi * 1000.0 * t))
    write_wav(after, 0.25 * np.sin(2.0 * np.pi * 1000.0 * t))
    checks.write_text(
        json.dumps(
            [
                {
                    "beforeFile": str(before),
                    "afterFile": str(after),
                    "metric": "compare.bandDeltas.200:2000.rmsDeltaDb",
                    "op": "<",
                    "value": -5,
                }
            ]
        ),
        encoding="utf-8",
    )

    code, payload = run_probe("check", str(checks), "--json")

    assert code == 0
    assert payload["passed"] is True


def test_check_supports_between_delta_boolean_and_diff_metrics(tmp_path: Path) -> None:
    before = tmp_path / "before.wav"
    after = tmp_path / "after.wav"
    checks = tmp_path / "checks.json"
    t = np.arange(48_000) / 48_000
    samples = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    write_wav(before, samples)
    write_wav(after, 0.25 * samples)
    checks.write_text(
        json.dumps(
            [
                {
                    "file": str(before),
                    "metric": "rmsDb",
                    "op": "between",
                    "value": [-10, -8],
                },
                {
                    "beforeFile": str(before),
                    "afterFile": str(after),
                    "metric": "rmsDb",
                    "op": "delta<",
                    "value": -5,
                },
                {
                    "file": str(before),
                    "metric": "monoCompatible",
                    "op": "==",
                    "value": True,
                },
                {
                    "beforeFile": str(before),
                    "afterFile": str(after),
                    "metric": "diff.residualRmsDb",
                    "op": ">",
                    "value": -20,
                },
            ]
        ),
        encoding="utf-8",
    )

    code, payload = run_probe("check", str(checks), "--json")

    assert code == 0
    assert payload["passed"] is True


def test_plot_writes_png(tmp_path: Path) -> None:
    audio = tmp_path / "sine.wav"
    out = tmp_path / "debug.png"
    samples = 0.5 * np.sin(2.0 * np.pi * 1000.0 * np.arange(48_000) / 48_000)
    write_wav(audio, samples)

    code, payload = run_probe("plot", str(audio), "--out", str(out))

    assert code == 0
    assert payload["out"] == str(out)
    assert out.read_bytes().startswith(b"\x89PNG")


def test_root_help_includes_agent_workflows() -> None:
    code, stdout, stderr = run_text("--help")

    assert code == 0
    assert stderr == ""
    assert "Common workflows:" in stdout
    assert "audio-probe list-metrics --json" in stdout
    assert "audio-probe loudness file.wav" in stdout
    assert "Windows are start:end seconds" in stdout
    assert "Exit codes:" in stdout


def test_list_metrics_exposes_check_metric_paths() -> None:
    code, payload = run_probe("list-metrics", "--json")

    assert code == 0
    names = {metric["name"] for metric in payload["metrics"]}
    assert "rmsDb" in names
    assert "bands.<low>:<high>.rmsDb" in names
    assert "clickScore" in names
    assert "lufsIntegrated" in names
    assert "phaseCorrelation" in names
    assert "diff.residualRmsDb" in names


def test_schema_describes_stable_outputs() -> None:
    code, payload = run_probe("schema", "--json")

    assert code == 0
    assert payload["commands"]["metrics"]["output"]["rmsDb"] == "number"
    assert payload["commands"]["loudness"]["output"]["lufsIntegrated"] == "number"
    assert payload["commands"]["check"]["input"]["metric"] == "metric path from list-metrics"


def test_version_is_machine_readable() -> None:
    code, payload = run_probe("version", "--json")

    assert code == 0
    assert payload["name"] == "audio-probe"
    assert payload["version"]
