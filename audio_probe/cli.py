from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .advanced import measure_diff, measure_loudness, measure_phase, measure_shape
from .audio import file_info, parse_bands, parse_window
from .checks import evaluate_check
from .measurements import (
    DEFAULT_BANDS,
    measure_bands,
    measure_compare,
    measure_envelope,
    measure_metrics,
    measure_stereo,
    measure_transients,
    write_plot,
)
from .discovery import EXAMPLES, METRICS, ROOT_HELP, SCHEMA


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

    diff = subparsers.add_parser("diff", help="align two files and measure null-test residual")
    diff.add_argument("before", help="baseline audio file")
    diff.add_argument("after", help="changed audio file")
    diff.add_argument("--window", help="time window as start:end seconds")
    diff.add_argument(
        "--no-align", action="store_true", help="skip cross-correlation alignment before subtracting"
    )
    diff.add_argument("--max-lag-ms", type=float, default=100.0, help="maximum alignment lag")
    diff.add_argument("--json", action="store_true", help="emit JSON")

    loudness = subparsers.add_parser("loudness", help="measure LUFS-style loudness")
    loudness.add_argument("file", help="audio file to analyze")
    loudness.add_argument("--window", help="time window as start:end seconds")
    loudness.add_argument("--json", action="store_true", help="emit JSON")

    phase = subparsers.add_parser("phase", help="measure phase and mono compatibility")
    phase.add_argument("file", help="audio file to analyze")
    phase.add_argument("--window", help="time window as start:end seconds")
    phase.add_argument("--json", action="store_true", help="emit JSON")

    shape = subparsers.add_parser("shape", help="measure file shape and optional shape delta")
    shape.add_argument("file", help="reference audio file")
    shape.add_argument("compare", nargs="?", help="optional candidate audio file")
    shape.add_argument("--silence-threshold-db", type=float, default=-60.0)
    shape.add_argument("--json", action="store_true", help="emit JSON")

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
    if args.command == "diff":
        return (
            measure_diff(
                args.before,
                args.after,
                parse_window(args.window),
                align=not args.no_align,
                max_lag_ms=args.max_lag_ms,
            ),
            0,
        )
    if args.command == "loudness":
        return measure_loudness(args.file, parse_window(args.window)), 0
    if args.command == "phase":
        return measure_phase(args.file, parse_window(args.window)), 0
    if args.command == "shape":
        return (
            measure_shape(
                args.file,
                args.compare,
                silence_threshold_db=args.silence_threshold_db,
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
