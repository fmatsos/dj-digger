# Duplicate Mastering and DJ Usability Analysis Design

**Category:** Future design. Nothing described here is implemented unless stated otherwise.

**Date:** 2026-08-28

## Goal

Extend exact-Chromaprint duplicate groups with mastering and DJ-usability observations while preserving the existing meaning of `best_quality`: the best available technical copy, ranked only from lossless state, bit depth, sample rate, bitrate, and the deterministic path tie-break.

The first version does not select a `best_dj_candidate`, modify audio files, normalize gain, compress, limit, or treat loudness or dynamic range as an objective quality score.

## Existing flow

The implemented duplicate path is:

```text
tracks / Track
    ↓
dj-digger duplicates
    ↓
DuplicateService
    ├── ChromaprintExtractor
    └── FFmpegProbe.probe_facts
    ↓
audio_fingerprints + technical_audio_metadata
    ↓
DuplicateRepository exact fingerprint groups
    ↓
QualitySelector technical ranking
    ↓
group JSON + track exports
```

`FFmpegProbe.probe()` already runs FFmpeg's `ebur128=peak=true` filter for the musical-analysis path and extracts summary Integrated LUFS, True Peak, and LRA values. Duplicate analysis deliberately uses only `probe_facts()` today, avoiding a full audio decode.

## Identity boundary

V1 analyzes only members of groups whose complete Chromaprint hashes are equal. It does not add duration tolerance, fingerprint similarity, edit detection, or remaster-oriented identity matching.

Mastering-variant detection is therefore opportunistic: it can compare mastering differences that occur inside exact groups, but it does not claim to discover every remaster in the library.

## Independent dimensions

The feature keeps three independent concepts:

```text
Audio identity
    └── exact Chromaprint

Technical quality
    └── existing QualitySelector and best_quality

Mastering / DJ usability
    ├── EBU R128 measurements
    ├── descriptive derived metrics
    └── review indicators
```

There is no combined `quality_score`. `best_quality` may be true while DJ usability is mediocre, or false while DJ usability is good.

## Analysis pipeline

The existing command is extended rather than replaced:

```text
duplicates --analyze --mastering
    ↓
fingerprints and technical facts
    ↓
exact duplicate groups
    ↓
members missing a compatible current mastering analysis
    ↓
bounded FFmpeg EBU R128 workers
    ↓
pure mastering and DJ calculations
    ↓
append-only attempt persistence
    ↓
latest-success mastering projection
    ↓
rebuildable target-dependent DJ projection
    ↓
computed group comparisons and review output
```

The heavy full-file decode is limited by default to present members of exact duplicate groups. Tracks outside duplicate groups are not decoded for mastering analysis. A future whole-library mode may reuse the service, but it is not exposed in V1.

The parent process owns all SQLite writes. Scheduler threads launch bounded FFmpeg child processes and return bounded structured results. Every successful track result is persisted promptly, making interrupted work resumable.

## FFmpeg measurements

The analyzer uses FFmpeg's native `ebur128` filter with true-peak measurement enabled. It captures:

- Integrated loudness in LUFS;
- Loudness Range in LU;
- True Peak in dBTP;
- the short-term loudness series emitted at regular intervals.

Structured `lavfi.r128.*` metadata is preferred for short-term samples. The implementation must not depend on locale-sensitive human log formatting when structured metadata is available.

Short-term samples are filtered to finite numeric values. P50 and P95 are calculated with one documented deterministic interpolation method. P95 represents sustained energetic passages more robustly than a single maximum. Integrated LUFS remains the global reference measurement.

All persisted measurements are numeric or null. The computation layer does not round intermediate values; presentation may apply stable rounding.

## Derived mastering and DJ metrics

The pure domain layer, independent of FFmpeg, calculates:

```text
peak_to_loudness_ratio_db = true_peak_dbtp - integrated_lufs

required_gain_db = dj_target_lufs - integrated_lufs

available_gain_db = dj_target_true_peak_dbtp - true_peak_dbtp

gain_deficit_db = max(0, required_gain_db - available_gain_db)
```

`required_gain_db` deliberately remains based on Integrated LUFS. `short_term_lufs_p95` is the active-loudness observation used separately in group comparisons, reducing the influence of long intros and outros without silently changing the documented gain formula.

Missing-value propagation is explicit:

- without Integrated LUFS, PLR, required gain, and gain deficit are null;
- without True Peak, PLR, available gain, and gain deficit are null;
- without usable short-term samples, P50 and P95 are null while other measurements remain usable;
- silence or very short input may produce a successful attempt containing null metrics;
- a process error or timeout produces a failed attempt and never invalidates indexing or fingerprints.

PLR and every other metric remain descriptive. No high or low value automatically means a better file.

## SQLite V9 persistence

The catalog upgrade follows the existing append-only facts and rebuildable projection pattern.

### `mastering_analysis`

One immutable row records each raw mastering attempt:

```text
id
track_id
analysis_version
input_size_bytes
input_mtime_ns
status                  succeeded | failed
error_stage
error_message
analyzed_at

integrated_lufs
loudness_range_lu
true_peak_dbtp
short_term_lufs_p50
short_term_lufs_p95
peak_to_loudness_ratio_db
```

Metric and error columns are nullable. Status and identity columns are constrained. The packaged SQL migration is atomic, rolls back fully on failure, and preserves existing V8 data.

### `current_mastering_analysis`

This rebuildable projection contains the latest successful compatible mastering attempt per track. A newer failed attempt does not replace the last success.

Reuse requires all of:

- current input size;
- current input modification time;
- the code-owned expected analysis version.

A version or input-identity change schedules a new FFmpeg attempt without rebuilding the rest of the catalog.

### `current_dj_analysis`

This rebuildable target-dependent projection persists the current DJ calculations:

```text
track_id PRIMARY KEY
mastering_analysis_id
dj_target_lufs
dj_target_true_peak_dbtp
required_gain_db
available_gain_db
gain_deficit_db
```

Changing either DJ target rebuilds this projection from current raw mastering measurements without decoding audio again. The mastering analysis version is owned and validated by the analyzer implementation, not accepted as arbitrary workspace configuration.

Group deltas and flags are not persisted. They are computed from current member projections so they cannot become stale when membership, thresholds, targets, or analyses change.

## Configuration

Initial configuration is explicit and recalibratable:

```toml
[mastering]
dj_target_lufs = -9.0
dj_target_true_peak_dbtp = -1.0

[mastering.variant_thresholds]
integrated_lufs_db = 1.5
active_loudness_db = 1.5
true_peak_db = 1.0
plr_db = 2.0
lra_lu = 1.5

[mastering.review_thresholds]
active_loudness_db = 1.5
true_peak_db = 1.0
plr_db = 2.0
gain_deficit_db = 1.5
```

These are provisional review heuristics, not mastering standards or final selection policy. Real-library listening calibration over approximately 20 to 50 representative groups will inform later values and any V1B `best_dj_candidate` policy.

## Group comparison

Every member is compared with the member currently marked `best_quality`:

```text
delta = member metric - best_quality member metric
```

The member comparison exposes nullable deltas for:

- Integrated LUFS;
- active loudness using short-term P95;
- True Peak;
- PLR;
- LRA;
- gain deficit.

Signed deltas are retained in output. Threshold decisions use `abs(delta) >= threshold`, so equally significant louder and quieter differences are treated symmetrically and the exact threshold boundary is included.

`mastering_variant` is true when at least one comparable member meets a configured variant threshold for Integrated LUFS, active loudness, True Peak, PLR, or LRA.

`dj_review_recommended` is true when at least one comparable member differs significantly from `best_quality` in active loudness, True Peak, PLR, or gain deficit.

Missing values are ignored for the affected comparison and never coerced to zero. A group without sufficient comparable current analyses reports an incomplete analysis state rather than a false negative.

If no `best_quality` selection exists, mastering measurements may still be produced and exposed, but comparison deltas and both group flags are null. The group reports `comparison_status = "missing_best_quality"` and is not returned by `--dj-review`. Mastering analysis never marks technical quality implicitly; callers that want comparisons can combine `--analyze --mastering --mark-best-quality` or run technical marking separately.

These flags request human review. They do not select a winner or modify `duplicate_quality_selections`.

## CLI contract

The existing lightweight behavior remains unchanged:

```bash
dj-digger duplicates --analyze
```

Heavy mastering analysis is opt-in:

```bash
dj-digger duplicates --analyze --mastering
```

Review output uses the existing list action:

```bash
dj-digger duplicates --list
dj-digger duplicates --list --dj-review
```

Rules:

- `--mastering` is valid only with `--analyze`;
- `--dj-review` is valid only with `--list`;
- existing `--source`, `--workers`, `--track-timeout`, `--background`, and `--json` behavior is reused;
- option compatibility is validated before opening the catalog;
- a per-track mastering failure produces a partial outcome without discarding successful fingerprint, technical, or mastering results;
- command-level initialization or catalog failures retain the existing fatal-error semantics.

The same worker bound applies to FFmpeg child processes. The per-track timeout bounds each fingerprint and mastering child independently. A member requiring both operations may therefore consume up to roughly twice `track_timeout`, plus bounded scheduler and persistence overhead.

## Output contract

Group JSON adds:

```json
{
  "group_id": "...",
  "mastering_variant": true,
  "dj_review_recommended": true,
  "analysis_complete": true,
  "members": [
    {
      "best_quality": true,
      "technical_facts": {},
      "audio_analysis": {
        "integrated_lufs": -10.8,
        "loudness_range_lu": 4.2,
        "true_peak_dbtp": -0.4,
        "short_term_lufs_p50": -9.8,
        "short_term_lufs_p95": -8.4,
        "peak_to_loudness_ratio_db": 10.4
      },
      "dj_analysis": {
        "required_gain_db": 1.8,
        "available_gain_db": -0.6,
        "gain_deficit_db": 2.4
      },
      "mastering_comparison": {
        "loudness_delta_db": 0.0,
        "active_loudness_delta_db": 0.0,
        "true_peak_delta_db": 0.0,
        "plr_delta_db": 0.0,
        "lra_delta_lu": 0.0,
        "gain_deficit_delta_db": 0.0,
        "mastering_variant": false
      }
    }
  ]
}
```

JSON remains nested. Existing JSON, CSV, and TSV track exports gain nullable, flattened per-track mastering fields without changing the meaning of existing fields.

The new `current_mastering_analysis` projection is authoritative for the new `integrated_lufs`, `loudness_range_lu`, `true_peak_dbtp`, short-term, and PLR export names. Legacy `technical_audio_metadata.loudness_lufs`, `true_peak_db`, and `dynamic_range` columns remain untouched for backward compatibility with the existing DSP path and are not silently overwritten or used as substitutes for the new fields.

`duplicates --list --dj-review` filters to recommended groups and sorts by:

1. maximum non-null member gain deficit descending;
2. maximum absolute comparable delta across the review metrics descending;
3. group identifier ascending.

Groups without a value for a sort metric sort after groups with a value.

The review representation includes path, codec, lossless state, sample rate, bit depth, `best_quality`, all persisted mastering and DJ metrics, and deltas relative to `best_quality`.

## Idempotence, interruption, and failures

An already compatible current success is reused without decoding. Successful results are persisted one track at a time by the parent. On interruption, a later run resumes from incompatible or missing tracks.

FFmpeg non-zero exits, malformed results, timeouts, silence, short files, unsupported streams, mono audio, lossy input, and lossless input are classified explicitly. Analysis failure never deletes or rewrites source audio and never invalidates scanning, technical facts, fingerprints, duplicate groups, or technical quality selections.

No shell invocation is used for media paths. Output parsing and stored error messages are bounded to avoid unbounded worker IPC or catalog growth.

## Verification strategy

### Pure calculations

- PLR and both documented gain examples;
- missing and non-finite inputs;
- P50/P95 interpolation and empty series;
- no qualitative PLR ranking.

### FFmpeg parsing

- Integrated LUFS, LRA, True Peak, and short-term metadata;
- incomplete and malformed output;
- silence, mono, and very short files;
- process failure, timeout, and interruption.

### Catalog

- preserving V8-to-V9 migration and fresh V9 schema;
- packaged SQL, atomic rollback on migration failure, and foreign-key integrity;
- immutable history and latest-success projection;
- a newer failure preserving the previous success;
- invalidation by input or version changes and target-only projection rebuild;
- transactional projection rebuild and parent-only persistence.

### Duplicate behavior

- heavy analysis limited to exact duplicate-group members;
- no mastering decode for isolated tracks;
- partial persistence and resumption;
- member deltas against `best_quality`;
- variant and review thresholds with missing metrics;
- unchanged technical ranking and `best_quality` behavior.

### CLI and exports

- full option matrix and exit codes;
- `--dj-review` filtering and deterministic sorting;
- nested JSON and nullable flattened tabular fields;
- second-run reuse and analysis-version invalidation.

### Public integration proof

A deterministic public fixture is generated with FFmpeg in a temporary directory, including lossless and lossy encodings plus a controlled transformation empirically shown to preserve the exact Chromaprint hash. The test first asserts fingerprint equality and actual duplicate-group membership, then executes the real CLI composition, inspects SQLite and exported artifacts, and verifies that source bytes are unchanged. If no deterministic transformation preserves the exact identity contract on the supported FFmpeg build, separate fixtures prove the real EBU path and the group-comparison path without falsely claiming one end-to-end mastering-variant fixture.

Final qualification includes focused and full pytest profiles, Ruff lint and format checks, strict mypy, migration and schema checks, wheel packaging, a real CLI smoke test, and FFmpeg runtime evidence. Private-library calibration is reported as unverified until explicitly run.

## Deferred V1B

V1 stores no `best_dj_candidate` selection. After reviewing and listening to approximately 20 to 50 representative real groups, a separate design will determine whether and how to select one using gain deficit, active loudness, True Peak, PLR, clipping observations, and technical quality. It must remain independent of `best_quality` and must not collapse the decision to the loudest file or the largest PLR.
