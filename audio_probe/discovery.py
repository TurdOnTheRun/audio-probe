from __future__ import annotations

ROOT_HELP = """audio-probe measures audio files and emits stable JSON for agents, tests, and CI.

Common workflows:
  audio-probe info file.wav --json
  audio-probe metrics file.wav --window 1.0:3.0 --json
  audio-probe bands file.wav --window 1.0:3.0 --bands 20:200,200:2000,2000:16000 --json
  audio-probe envelope file.wav --window-ms 50 --hop-ms 10 --json
  audio-probe stereo file.wav --window 1.0:3.0 --json
  audio-probe compare before.wav after.wav --window 1.0:3.0 --json
  audio-probe diff before.wav after.wav --window 1.0:3.0 --json
  audio-probe loudness file.wav --window 1.0:3.0 --json
  audio-probe phase file.wav --window 1.0:3.0 --json
  audio-probe shape file.wav changed.wav --json
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
        "description": "Null-test two files after alignment and report residual energy.",
        "command": "audio-probe diff before.wav after.wav --window 1.0:3.0 --json",
    },
    {
        "description": "Measure LUFS-style loudness, loudness range, and true peak.",
        "command": "audio-probe loudness render.wav --window 1.0:3.0 --json",
    },
    {
        "description": "Measure phase correlation, stereo width, and mono compatibility.",
        "command": "audio-probe phase stereo.wav --window 1.0:3.0 --json",
    },
    {
        "description": "Inspect duration, format shape, and leading/trailing silence.",
        "command": "audio-probe shape before.wav after.wav --json",
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
        "name": "silenceDurationSeconds",
        "type": "number",
        "unit": "seconds",
        "commands": ["metrics", "check"],
        "description": "Total duration of ranges whose envelope RMS is below the silence threshold.",
    },
    {
        "name": "onsetCount",
        "type": "integer",
        "unit": "count",
        "commands": ["metrics", "check"],
        "description": "Number of detected envelope rises.",
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
        "name": "lufsIntegrated",
        "type": "number",
        "unit": "LUFS",
        "commands": ["loudness", "check"],
        "description": "Integrated gated LUFS-style loudness.",
    },
    {
        "name": "lufsMomentaryMax",
        "type": "number",
        "unit": "LUFS",
        "commands": ["loudness", "check"],
        "description": "Maximum 400 ms loudness block.",
    },
    {
        "name": "lufsShortTermMax",
        "type": "number",
        "unit": "LUFS",
        "commands": ["loudness", "check"],
        "description": "Maximum 3 second loudness block.",
    },
    {
        "name": "loudnessRangeLufs",
        "type": "number",
        "unit": "LU",
        "commands": ["loudness", "check"],
        "description": "Approximate loudness range from short-term loudness percentiles.",
    },
    {
        "name": "truePeakDb",
        "type": "number",
        "unit": "dBFS",
        "commands": ["loudness", "check"],
        "description": "Oversampled true peak estimate.",
    },
    {
        "name": "phaseCorrelation",
        "type": "number",
        "unit": "ratio",
        "commands": ["phase", "check"],
        "description": "Left/right phase correlation from -1 to 1.",
    },
    {
        "name": "stereoWidth",
        "type": "number",
        "unit": "ratio",
        "commands": ["phase", "check"],
        "description": "Side RMS divided by mid RMS.",
    },
    {
        "name": "monoDeltaDb",
        "type": "number",
        "unit": "dB",
        "commands": ["phase", "check"],
        "description": "Mono summed level minus stereo RMS level.",
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
    {
        "name": "transientCount",
        "type": "integer",
        "unit": "count",
        "commands": ["transients", "check"],
        "description": "Count of separated sample-jump transients.",
    },
    {
        "name": "durationSeconds",
        "type": "number",
        "unit": "seconds",
        "commands": ["shape", "check"],
        "description": "File duration.",
    },
    {
        "name": "leadingSilenceSeconds",
        "type": "number",
        "unit": "seconds",
        "commands": ["shape", "check"],
        "description": "Leading silence duration.",
    },
    {
        "name": "trailingSilenceSeconds",
        "type": "number",
        "unit": "seconds",
        "commands": ["shape", "check"],
        "description": "Trailing silence duration.",
    },
    {
        "name": "compare.bandDeltas.<low>:<high>.rmsDeltaDb",
        "type": "number",
        "unit": "dB",
        "commands": ["compare", "check"],
        "description": "After-minus-before RMS delta for a selected band.",
    },
    {
        "name": "diff.residualRmsDb",
        "type": "number",
        "unit": "dBFS",
        "commands": ["diff", "check"],
        "description": "Aligned null-test residual RMS.",
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
                "silenceDurationSeconds": "number",
                "onsetTimes": ["number"],
                "onsetCount": "integer",
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
        "diff": {
            "output": {
                "beforeFile": "string",
                "afterFile": "string",
                "window": {"start": "number", "end": "number"},
                "sampleOffset": "integer",
                "timeOffsetSeconds": "number",
                "comparedFrames": "integer",
                "durationDeltaSeconds": "number",
                "residualRmsDb": "number",
                "residualPeakDb": "number",
                "residualToBeforeDb": "number",
            }
        },
        "loudness": {
            "output": {
                "file": "string",
                "window": {"start": "number", "end": "number"},
                "lufsIntegrated": "number",
                "lufsMomentaryMax": "number",
                "lufsShortTermMax": "number",
                "loudnessRangeLufs": "number",
                "truePeakDb": "number",
                "truePeak": "number",
            }
        },
        "phase": {
            "output": {
                "file": "string",
                "window": {"start": "number", "end": "number"},
                "phaseCorrelation": "number",
                "stereoWidth": "number",
                "monoRmsDb": "number",
                "monoDeltaDb": "number",
                "monoCompatible": "boolean",
            }
        },
        "shape": {
            "output": {
                "file": "string",
                "durationSeconds": "number",
                "sampleRate": "integer",
                "channels": "integer",
                "frames": "integer",
                "leadingSilenceSeconds": "number",
                "trailingSilenceSeconds": "number",
                "activeDurationSeconds": "number",
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
                "transientCount": "integer",
                "transientTimes": ["number"],
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
