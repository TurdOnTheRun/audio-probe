from __future__ import annotations

import operator
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .advanced import measure_diff, measure_loudness, measure_phase, measure_shape
from .audio import parse_bands, parse_window, round_float
from .measurements import (
    measure_bands,
    measure_compare,
    measure_metrics,
    measure_stereo,
    measure_transients,
)


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
        actual = round_float(float(after) - float(before))
    else:
        actual = resolve_check_metric(check)

    passed = compare_values(actual, op, expected)
    return {
        "check": check,
        "actual": actual,
        "passed": passed,
    }


def resolve_check_metric(check: dict[str, Any]) -> float | bool:
    metric_path = check["metric"]
    if metric_path.startswith(("compare.", "diff.")):
        before_file = check.get("beforeFile") or check.get("before") or check.get("file")
        after_file = check.get("afterFile") or check.get("after") or check.get("compareFile")
        if not before_file or not after_file:
            raise ValueError(f"{metric_path} checks require beforeFile and afterFile")
        return resolve_pair_metric(before_file, after_file, metric_path, check.get("window"))
    return resolve_metric(check["file"], metric_path, check.get("window"))


def resolve_pair_metric(
    before_path: str | Path,
    after_path: str | Path,
    metric_path: str,
    window_value: str | None = None,
) -> float:
    window = parse_window(window_value)
    if metric_path.startswith("compare.bandDeltas."):
        parts = metric_path.split(".")
        if len(parts) != 4 or parts[3] != "rmsDeltaDb":
            raise ValueError(f"unsupported compare band metric path: {metric_path}")
        result = measure_compare(before_path, after_path, window, parse_bands(parts[2]))
        return float(result["bandDeltas"][0]["rmsDeltaDb"])
    if metric_path.startswith("compare."):
        result = measure_compare(before_path, after_path, window)
        return float(_nested(result, metric_path.removeprefix("compare.")))
    if metric_path.startswith("diff."):
        result = measure_diff(before_path, after_path, window)
        return float(_nested(result, metric_path.removeprefix("diff.")))
    raise ValueError(f"unsupported pair metric path: {metric_path}")


def resolve_metric(
    path: str | Path,
    metric_path: str,
    window_value: str | None = None,
) -> float | bool:
    window = parse_window(window_value)
    if metric_path.startswith("bands."):
        parts = metric_path.split(".")
        if len(parts) != 3 or parts[2] != "rmsDb":
            raise ValueError(f"unsupported band metric path: {metric_path}")
        bands = parse_bands(parts[1])
        return float(measure_bands(path, bands, window)["bands"][0]["rmsDb"])

    if metric_path in {"leftRmsDb", "rightRmsDb", "balance", "stereoBalance"}:
        return float(measure_stereo(path, window)[metric_path])

    if metric_path in {
        "maxSampleJump",
        "maxSampleJumpDb",
        "highFrequencyBurstDb",
        "clickScore",
        "transientCount",
    }:
        return float(measure_transients(path, window)[metric_path])

    if metric_path in {
        "lufsIntegrated",
        "lufsMomentaryMax",
        "lufsShortTermMax",
        "loudnessRangeLufs",
        "truePeakDb",
        "truePeak",
    }:
        return float(measure_loudness(path, window)[metric_path])

    if metric_path in {"phaseCorrelation", "stereoWidth", "monoRmsDb", "monoDeltaDb"}:
        return float(measure_phase(path, window)[metric_path])
    if metric_path == "monoCompatible":
        return bool(measure_phase(path, window)[metric_path])

    if metric_path in {
        "durationSeconds",
        "sampleRate",
        "channels",
        "frames",
        "leadingSilenceSeconds",
        "trailingSilenceSeconds",
        "activeDurationSeconds",
    }:
        return float(measure_shape(path)[metric_path])

    metrics = measure_metrics(path, window)
    if metric_path not in metrics:
        raise ValueError(f"unsupported metric path: {metric_path}")
    return float(metrics[metric_path])


def compare_values(actual: float | bool, op: str, expected: Any) -> bool:
    if isinstance(actual, bool):
        if op != "==":
            raise ValueError("boolean metrics only support ==")
        return actual == bool(expected)

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
    return operations[op](float(actual), float(expected))


def _nested(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"unsupported metric path: {path}")
        current = current[part]
    return current
