# Audio Probe

Objective audio analysis for agents, tests, and CI.

`audio-probe` reads audio files, computes measurable properties, and emits stable JSON so automated tests can decide whether audio behavior changed as expected.

## Highlights

- File metadata, level metrics, band energy, envelopes, stereo balance, comparisons, null diffs, loudness, phase, shape checks, transient checks, plots, and generic checks.
- Deterministic JSON output designed for automation.
- Works on WAV, FLAC, AIFF, OGG, and other formats supported by libsndfile.
- Synthetic fixture generator for repeatable tests.

## Install

```sh
pipx install audio-probe
```

For local development:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev,plot]"
```

## Quickstart

```sh
audio-probe info fixtures/sine-1000hz.wav --json
audio-probe metrics fixtures/sine-1000hz.wav --window 0.0:1.0 --json
audio-probe bands fixtures/sine-1000hz.wav --bands 20:200,200:2000,2000:16000 --json
audio-probe envelope fixtures/pulse.wav --window-ms 50 --hop-ms 10 --json
audio-probe stereo stereo.wav --window 1.0:3.0 --json
audio-probe compare before.wav after.wav --window 1.0:3.0 --json
audio-probe diff before.wav after.wav --window 1.0:3.0 --json
audio-probe loudness fixtures/sine-1000hz.wav --json
audio-probe phase stereo.wav --window 1.0:3.0 --json
audio-probe shape before.wav after.wav --json
audio-probe transients fixtures/click-loop.wav --window 0.0:1.0 --json
audio-probe plot fixtures/sine-1000hz.wav --out debug.png
audio-probe check checks.json --json
audio-probe examples --json
audio-probe list-metrics --json
audio-probe schema --json
audio-probe version --json
```

## Commands

### `info`

```sh
audio-probe info file.wav --json
```

Returns file path, duration, sample rate, channel count, and frame count.

### `metrics`

```sh
audio-probe metrics file.wav --window 2.0:4.0 --json
```

Returns `rmsDb`, `peakDb`, `crestFactorDb`, `clippingSamples`, `dcOffset`, `spectralCentroidHz`, `silenceRanges`, `onsetTimes`, and `decaySlopeDbPerSecond`.

### `bands`

```sh
audio-probe bands file.wav --window 2.0:4.0 --bands 20:200,200:2000,2000:16000 --json
```

Returns per-band RMS level in dBFS.

### `envelope`

```sh
audio-probe envelope file.wav --window-ms 50 --hop-ms 10 --json
```

Returns frame-level RMS and peak values plus `maxEnvelopeStepDb`.

### `stereo`

```sh
audio-probe stereo file.wav --window 1.0:3.0 --json
```

Returns left and right RMS levels plus `balance`, where positive means left-heavy and negative means right-heavy.

### `compare`

```sh
audio-probe compare before.wav after.wav --window 1.0:3.0 --json
```

Returns after-minus-before deltas for RMS, peak, and configured bands.

### `diff`

```sh
audio-probe diff before.wav after.wav --window 1.0:3.0 --json
```

Aligns two files by cross-correlation, subtracts before from after, and returns residual RMS/peak levels, offset, compared frame count, and duration delta. Pass `--no-align` to subtract without alignment.

### `loudness`

```sh
audio-probe loudness file.wav --window 1.0:3.0 --json
```

Returns LUFS-style integrated loudness, momentary and short-term maxima, approximate loudness range, and oversampled true peak.

### `phase`

```sh
audio-probe phase stereo.wav --window 1.0:3.0 --json
```

Returns phase correlation, stereo width, mono RMS level, mono level delta, and `monoCompatible`.

### `shape`

```sh
audio-probe shape before.wav after.wav --json
```

Returns duration, sample rate, channel count, frame count, leading/trailing silence, and active duration. With a second file, also returns duration/frame deltas and sample-rate/channel match booleans.

### `transients`

```sh
audio-probe transients file.wav --window 3.95:4.05 --json
```

Returns `maxSampleJump`, `maxSampleJumpDb`, `highFrequencyBurstDb`, `clickScore`, `transientCount`, and `transientTimes`.

### `plot`

```sh
audio-probe plot file.wav --out debug.png
```

Writes a debug image with waveform, envelope, and spectrogram. Install with the `plot` extra to enable this command.

### `check`

```sh
audio-probe check checks.json --json
```

Example:

```json
[
  {
    "file": "wet.wav",
    "metric": "bands.2000:16000.rmsDb",
    "window": "1.0:3.0",
    "op": "<",
    "value": -40
  },
  {
    "file": "render.wav",
    "metric": "rmsDb",
    "window": "4.0:5.0",
    "op": "<",
    "value": -60
  }
]
```

Supported operators: `<`, `<=`, `>`, `>=`, `==`, `between`, `delta<`, and `delta>`.

For delta checks, provide `beforeFile` and `afterFile`:

```json
{
  "beforeFile": "before.wav",
  "afterFile": "after.wav",
  "metric": "rmsDb",
  "window": "1.0:3.0",
  "op": "delta<",
  "value": -3
}
```

The command exits with code `0` when all checks pass and `1` when any check fails.

### Agent Discovery

```sh
audio-probe examples --json
audio-probe list-metrics --json
audio-probe schema --json
audio-probe version --json
```

These commands are intended for agents and scripts that need to discover valid workflows, metric paths, JSON output shapes, and version information without scraping README text.

`audio-probe --help` also includes common workflows, window syntax, band syntax, discovery commands, and exit codes.

## Fixtures

Generate deterministic fixture audio:

```sh
python scripts/generate_fixtures.py
```

Fixtures:

- `sine-100hz.wav`
- `sine-1000hz.wav`
- `sine-8000hz.wav`
- `noise-white.wav`
- `noise-pink.wav`
- `pulse.wav`
- `click-loop.wav`
- `sustained-pad.wav`
- `impulse.wav`

## Metric Paths

Checks can reference top-level metric fields such as `rmsDb`, `peakDb`, `spectralCentroidHz`, `silenceDurationSeconds`, `onsetCount`, `maxSampleJump`, `transientCount`, `leftRmsDb`, `rightRmsDb`, `balance`, `lufsIntegrated`, `truePeakDb`, `phaseCorrelation`, `stereoWidth`, `durationSeconds`, `leadingSilenceSeconds`, and `trailingSilenceSeconds`.

Band checks use:

```text
bands.<low>:<high>.rmsDb
```

Example:

```text
bands.2000:16000.rmsDb
```

Compare band checks use:

```text
compare.bandDeltas.<low>:<high>.rmsDeltaDb
```

Null-diff checks use:

```text
diff.residualRmsDb
```

## License

MIT
