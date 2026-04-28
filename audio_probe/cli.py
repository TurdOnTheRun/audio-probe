from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .audio import file_info, parse_bands, parse_window
from .measurements import (
    DEFAULT_BANDS,
    evaluate_check,
    measure_bands,
    measure_compare,
    measure_envelope,
    measure_metrics,
    measure_stereo,
    measure_transients,
    write_plot,
)

ROOT_HELP = """audio-probe measures audio files and emits stable JSON for agents, tests, and CI.

Common workflows:
  audio-probe info file.wav --json
  audio-probe metrics file.wav --window 1.0:3.0 --json
  audio-probe bands file.wav --window 1.0:3.0 --bands 20:200,200:2000,2000:16000 --json
  audio-probe envelope file.wav --window-ms 50 --hop-ms 10 --json
  audio-probe stereo file.wav --window 1.0:3.0 --json
  audio-probe compare before.wav after.wav --window 1.0:3.0 --json
  audio-probe transients file.wav --window 3.95:4.05 --json
  audio-probe plot file.wav --out debug.png
  audio-probe check checks.json --json

Syntax:
  Windows are start:end seconds, for example 1.0:3.0. Empty end means EOF.
  Bands are low:high Hz ranges, comma-separated, for example 20:200,200:2000.

Agent discovery:
  audio-probe examples --json
  audio-probe list-metrics --json
  audio-probe schema --json
  audio-probe version --json

Exit codes:
  0  success, or all checks passed
  1  one or more checks failed
  2  usage or runtime error
"""

EXAMPLES = [
    {
        "description": "Inspect basic file metadata.",
        "command": "audio-probe info fixtures/sine-1000hz.wav --json",
    },
    {
        "description": "Measure whole-file RMS, peak, clipping, DC offset, centroid, silence, onsets, and decay.",
        "command": "audio-probe metrics fixtures/sine-1000hz.wav --json",
    },
    {
        "description": "Measure metrics inside a time window.",
        "command": "audio-probe metrics render.wav --window 1.0:3.0 --json",
    },
    {
        "description": "Measure energy in low, mid, and high frequency bands.",
        "command": (
            "audio-probe bands render.wav --window 1.0:3.0 "
            "--bands 20:200,200:2000,2000:16000 --json"
        ),
    },
    {
        "description": "Generate a frame-by-frame level envelope.",
        "command": "audio-probe envelope render.wav --window-ms 50 --hop-ms 10 --json",
    },
    {
        "description": "Measure stereo balance; positive balance means left-heavy.",
        "command": "audio-probe stereo stereo.wav --window 1.0:3.0 --json",
    },
    {
        "description": "Compare after-minus-before level and band deltas.",
        "command": "audio-probe compare before.wav after.wav --window 1.0:3.0 --json",
    },
    {
        "description": "Measure discontinuities and click-like high-frequency bursts.",
        "command": "audio-probe transients render.wav --window 3.95:4.05 --json",
    },
    {
        "description": "Create a debug image with waveform, envelope, and spectrogram.",
        "command": "audio-probe plot render.wav --out debug.png",
    },
    {
        "description": "Run generic JSON checks and return nonzero when any check fails.",
        "command": "audio-probe check checks.json --json",
    },
]

METRICS = [
    {
        "name": "rmsDb",
        "type": "number",
        "unit": "dBFS",
        "commands": ["metrics", "check"],
        "description": "Root-mean-square level over the selected window.",
    },
    {
        "name": "peakDb",
        "type": "number",
        "unit": "dBFS",
        "commands": ["metrics", "check"],
        "description": "Peak absolute sample level over the selected window.",
    },
    {
        "name": "crestFactorDb",
        "type": "number",
        "unit": "dB",
        "commands": ["metrics"],
        "description": "Peak level minus RMS level.",
    },
    {
        "name": "clippingSamples",
        "type": "integer",
        "unit": "samples",
        "commands": ["metrics"],
        "description": "Samples whose absolute value is near full scale.",
    },
    {
        "name": "dcOffset",
        "type": "number",
        "unit": "amplitude",
        "commands": ["metrics"],
        "description": "Mean sample value over the selected window.",
    },
    {
        "name": "spectralCentroidHz",
        "type": "number",
        "unit": "Hz",
        "commands": ["metrics"],
        "description": "Magnitude-weighted average frequency.",
    },
    {
        "name": "silenceRanges",
        "type": "array",
        "unit": "seconds",
        "commands": ["metrics"],
        "description": "Ranges whose envelope RMS is below the silence threshold.",
    },
    {
        "name": "onsetTimes",
        "type": "array",
        "unit": "seconds",
        "commands": ["metrics"],
        "description": "Envelope rise times that look like onsets.",
    },
    {
        "name": "decaySlopeDbPerSecond",
        "type": "number",
        "unit": "dB/s",
        "commands": ["metrics"],
        "description": "Linear fitted level slope after the envelope peak.",
    },
    {
        "name": "bands.<low>:<high>.rmsDb",
        "type": "number",
        "unit": "dBFS",
        "commands": ["bands", "check"],
        "description": "RMS level inside a frequency band, for example bands.2000:16000.rmsDb.",
    },
    {
        "name": "leftRmsDb",
        "type": "number",
        "unit": "dBFS",
        "commands": ["stereo", "check"],
        "description": "Left channel RMS level.",
    },
    {
        "name": "rightRmsDb",
        "type": "number",
        "unit": "dBFS",
        "commands": ["stereo", "check"],
        "description": "Right channel RMS level.",
    },
    {
        "name": "balance",
        "type": "number",
        "unit": "ratio",
        "commands": ["stereo", "check"],
        "description": "(leftRms - rightRms) / (leftRms + rightRms). Positive means left-heavy.",
    },
    {
        "name": "maxEnvelopeStepDb",
        "type": "number",
        "unit": "dB",
        "commands": ["envelope"],
        "description": "Largest absolute RMS step between adjacent envelope frames.",
    },
    {
        "name": "maxSampleJump",
        "type": "number",
        "unit": "amplitude",
        "commands": ["transients", "check"],
        "description": "Largest absolute difference between adjacent mono samples.",
    },
    {
        "name": "maxSampleJumpDb",
        "type": "number",
        "unit": "dBFS",
        "commands": ["transients", "check"],
        "description": "maxSampleJump converted to dBFS.",
    },
    {
        "name": "highFrequencyBurstDb",
        "type": "number",
        "unit": "dBFS",
        "commands": ["transients", "check"],
        "description": "High-frequency energy level useful for click detection.",
    },
    {
        "name": "clickScore",
        "type": "number",
        "unit": "ratio",
        "commands": ["transients", "check"],
        "description": "0..1 transient score derived from sample jumps relative to peak.",
    },
]

SCHEMA = {
    "jsonStability": "Field names and units are intended to remain stable within a major version.",
    "windowSyntax": "start:end seconds, for example 1.0:3.0. Empty end means EOF.",
    "bandSyntax": "low:high Hz ranges, comma-separated, for example 20:200,200:2000.",
    "exitCodes": {
        "0": "success or all checks passed",
        "1": "check failure",
        "2": "usage or runtime error",
    },
    "commands": {
        "info": {
            "output": {
                "file": "string",
                "durationSeconds": "number",
                "sampleRate": "integer",
                "channels": "integer",
                "frames": "integer",
            }
        },
        "metrics": {
            "output": {
                "file": "string",
                "window": {"start": "number", "end": "number"},
                "rmsDb": "number",
                "peakDb": "number",
                "crestFactorDb": "number",
                "clippingSamples": "integer",
                "dcOffset": "number",
                "spectralCentroidHz": "number",
                "silenceRanges": [{"start": "number", "end": "number"}],
                "onsetTimes": ["number"],
                "decaySlopeDbPerSecond": "number",
            }
        },
        "bands": {
            "output": {
                "file": "string",
                "window": {"start": "number", "end": "number"},
                "bands": [{"rangeHz": ["number", "number"], "rmsDb": "number"}],
            }
        },
        "envelope": {
            "output": {
                "file": "string",
                "windowMs": "number",
                "hopMs": "number",
                "frames": [{"time": "number", "rmsDb": "number", "peakDb": "number"}],
                "maxEnvelopeStepDb": "number",
            }
        },
        "stereo": {
            "output": {
                "file": "string",
                "window": {"start": "number", "end": "number"},
                "leftRmsDb": "number",
                "rightRmsDb": "number",
                "balance": "number",
                "stereoBalance": "number",
            }
        },
        "compare": {
            "output": {
                "beforeFile": "string",
                "afterFile": "string",
                "window": {"start": "number", "end": "number"},
                "rmsDeltaDb": "number",
                "peakDeltaDb": "number",
                "bandDeltas": [{"rangeHz": ["number", "number"], "rmsDeltaDb": "number"}],
            }
        },
        "transients": {
            "output": {
                "file": "string",
                "window": {"start": "number", "end": "number"},
                "maxSampleJump": "number",
                "maxSampleJumpDb": "number",
                "highFrequencyBurstDb": "number",
                "clickScore": "number",
            }
        },
        "check": {
            "input": {
                "file": "string",
                "metric": "metric path from list-metrics",
                "window": "optional start:end seconds",
                "op": "< | <= | > | >= | == | between | delta< | delta>",
                "value": "number or [low, high] for between",
            },
            "output": {
                "passed": "boolean",
                "results": [{"check": "object", "actual": "number", "passed": "boolean"}],
            },
        },
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result, exit_code = run_command(args)
    except Exception as error:
        print(f"audio-probe: error: {error}", file=sys.stderr)
        return 2

    if result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audio-probe",
        description="Objective audio analysis with stable JSON output.",
        epilog=ROOT_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="show file metadata")
    info.add_argument("file", help="audio file to inspect")
    info.add_argument("--json", action="store_true", help="emit JSON")

    metrics = subparsers.add_parser("metrics", help="measure level and signal metrics")
    metrics.add_argument("file", help="audio file to analyze")
    metrics.add_argument("--window", help="time window as start:end seconds")
    metrics.add_argument("--json", action="store_true", help="emit JSON")

    bands = subparsers.add_parser("bands", help="measure frequency band energy")
    bands.add_argument("file", help="audio file to analyze")
    bands.add_argument("--window", help="time window as start:end seconds")
    bands.add_argument(
        "--bands", default=DEFAULT_BANDS, help="comma-separated ranges such as 20:200,200:2000"
    )
    bands.add_argument("--json", action="store_true", help="emit JSON")

    envelope = subparsers.add_parser("envelope", help="measure frame-level RMS and peak")
    envelope.add_argument("file", help="audio file to analyze")
    envelope.add_argument(
        "--window-ms", type=float, default=50.0, help="analysis frame size in milliseconds"
    )
    envelope.add_argument(
        "--hop-ms", type=float, default=10.0, help="frame hop size in milliseconds"
    )
    envelope.add_argument("--json", action="store_true", help="emit JSON")

    stereo = subparsers.add_parser("stereo", help="measure stereo balance")
    stereo.add_argument("file", help="audio file to analyze")
    stereo.add_argument("--window", help="time window as start:end seconds")
    stereo.add_argument("--json", action="store_true", help="emit JSON")

    compare = subparsers.add_parser("compare", help="compare two files")
    compare.add_argument("before", help="baseline audio file")
    compare.add_argument("after", help="changed audio file")
    compare.add_argument("--window", help="time window as start:end seconds")
    compare.add_argument(
        "--bands", default=DEFAULT_BANDS, help="comma-separated ranges such as 20:200,200:2000"
    )
    compare.add_argument("--json", action="store_true", help="emit JSON")

    transients = subparsers.add_parser(
        "transients", help="measure discontinuities and click-like bursts"
    )
    transients.add_argument("file", help="audio file to analyze")
    transients.add_argument("--window", help="time window as start:end seconds")
    transients.add_argument("--json", action="store_true", help="emit JSON")

    plot = subparsers.add_parser("plot", help="write waveform, envelope, and spectrogram image")
    plot.add_argument("file", help="audio file to plot")
    plot.add_argument("--out", required=True, help="output PNG path")

    check = subparsers.add_parser("check", help="run generic JSON checks")
    check.add_argument("checks", help="JSON check file")
    check.add_argument("--json", action="store_true", help="emit JSON")

    examples = subparsers.add_parser("examples", help="show copyable usage examples")
    examples.add_argument("--json", action="store_true", help="emit JSON")

    list_metrics = subparsers.add_parser("list-metrics", help="list supported metric paths")
    list_metrics.add_argument("--json", action="store_true", help="emit JSON")

    schema = subparsers.add_parser("schema", help="describe stable JSON outputs")
    schema.add_argument("--json", action="store_true", help="emit JSON")

    version = subparsers.add_parser("version", help="show version information")
    version.add_argument("--json", action="store_true", help="emit JSON")

    return parser


def run_command(args: argparse.Namespace) -> tuple[dict[str, Any] | None, int]:
    if args.command == "examples":
        return {"examples": EXAMPLES}, 0
    if args.command == "list-metrics":
        return {"metrics": METRICS}, 0
    if args.command == "schema":
        return SCHEMA, 0
    if args.command == "version":
        return {"name": "audio-probe", "version": __version__}, 0
    if args.command == "info":
        return file_info(args.file), 0
    if args.command == "metrics":
        return measure_metrics(args.file, parse_window(args.window)), 0
    if args.command == "bands":
        return measure_bands(args.file, parse_bands(args.bands), parse_window(args.window)), 0
    if args.command == "envelope":
        return measure_envelope(args.file, window_ms=args.window_ms, hop_ms=args.hop_ms), 0
    if args.command == "stereo":
        return measure_stereo(args.file, parse_window(args.window)), 0
    if args.command == "compare":
        return (
            measure_compare(
                args.before,
                args.after,
                parse_window(args.window),
                parse_bands(args.bands),
            ),
            0,
        )
    if args.command == "transients":
        return measure_transients(args.file, parse_window(args.window)), 0
    if args.command == "plot":
        return write_plot(args.file, args.out), 0
    if args.command == "check":
        return run_checks(args.checks)
    raise ValueError(f"unsupported command: {args.command}")


def run_checks(path: str | Path) -> tuple[dict[str, Any], int]:
    with Path(path).open("r", encoding="utf-8") as handle:
        checks = json.load(handle)
    if not isinstance(checks, list):
        raise ValueError("checks file must contain a JSON array")

    results = [evaluate_check(check) for check in checks]
    passed = all(result["passed"] for result in results)
    return {"passed": passed, "results": results}, 0 if passed else 1
