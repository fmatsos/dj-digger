# Bounded-Memory Audio Analysis Design

## Goal

Make full-library `refresh` and `analyze` runs use bounded memory, preserve every completed
track immediately, and recover aggregate runs automatically after an external interruption.
The CLI surface and the meaning of successful, partial, failed, and reused analyses remain
compatible.

## Scope

This change covers three coupled defects:

1. Full-track `float64` copies are passed through the rhythm and spectral paths even though
   Essentia consumes single-precision arrays.
2. Spectral extraction materializes every frame spectrum and multiple whole-track matrices.
3. The pipeline retains every outcome and persists the aggregate run only after all tracks
   finish.

It does not add configuration knobs, change DSP bands or window sizes, or introduce per-track
subprocesses. The project intentionally drops all historical analysis/catalog compatibility:
only the current persistence lifecycle, current database schema, and canonical exports remain.

## Current-Only Compatibility Policy

The incremental lifecycle replaces the old aggregate and one-off persistence APIs. Legacy
outcome tuples, `persist_run`, `store_success`, and `store_failure` are removed rather than
adapted.

Database initialization uses one consolidated current schema. An empty database is initialized;
a database carrying any former schema version is rejected with an actionable recreation error.
No v1-v5 upgrade path remains.

Legacy CSV/TSV/text exports, their repository, and `export.legacy_compatibility` are removed.
Only canonical track, artifact, and analysis outputs remain. A configuration containing the old
`[export]` compatibility table is rejected instead of silently ignored.

## Data Types and DSP Memory

Decoded mono 48 kHz samples remain `numpy.float32` throughout the full-track path.
`RhythmAnalyzer`, `EssentiaRhythmAdapter`, and `EssentiaKeyAdapter` accept single-precision
samples directly. No full-track `astype(float64)` or `asarray(..., dtype=float64)` copy is
allowed.

`NumpySpectrumAdapter` processes one overlapping FFT frame at a time. It retains only:

- the current frame spectrum;
- the previous frame spectrum for positive spectral flux;
- the sum of magnitudes per frequency bin;
- scalar flux totals and counts.

At completion it derives the existing mean spectrum, configured band values, onset value,
and spectral centroid from those accumulators. Short-input padding and empty-input behavior
remain compatible. Floating-point assertions use tolerances because accumulation order may
change the least significant digits.

This bounds adapter memory by FFT size rather than track duration, excluding the decoded
single-precision audio required by the current standard-mode Essentia algorithms.

## Incremental Run Persistence

An aggregate analysis run is inserted with status `running` before extraction begins. Reused
tracks contribute to the run counters but do not create duplicate attempts.

Each completed extraction outcome is persisted immediately in its own transaction:

- a success inserts its immutable analysis attempt, sections, and completion event;
- a failure inserts its failed attempt and failure event;
- the aggregate run counters are updated in the same transaction as the outcome.

The pipeline does not retain completed outcomes. After all selected pending tracks have
completed, it finalizes the aggregate run with a completion timestamp and derives its status:

- `succeeded` when no extraction failed;
- `partial` when at least one track was completed or reused and at least one failed;
- `failed` when failures exist and no track was completed or reused.

An empty run remains `succeeded`.

## Bounded Concurrency

`workers` remains supported. The pipeline keeps no more than `workers` extraction futures in
flight. As soon as a future completes, its outcome is persisted and one new track may be
submitted. Completion and event order may therefore differ from lexical track order when
`workers > 1`; aggregate counts and exported ordering remain deterministic.

The default `workers=1` processes and commits one track at a time.

## Interrupted-Run Recovery

Before a new analysis run starts, persistence reconciles every older compatible or
incompatible aggregate run still marked `running`. It counts that run's persisted successful
and failed attempts, preserves its recorded reused count, sets `finished_at`, refreshes the
counters, and assigns:

- `partial` when at least one success or reuse exists alongside a failure or unfinished work;
- `failed` when nothing succeeded or was reused;
- `succeeded` only when recorded outcomes account for all eligible tracks without failure.

Unaccounted eligible tracks are treated as interrupted work, not as failed attempts. They
remain pending and are eligible for the new run. Recovery is idempotent and creates no audio
attempt or track event.

## Failure Boundaries

Every outcome transaction is atomic. Invalid section data or a database error rolls back that
outcome and its counter update. The aggregate run remains `running`; the next invocation
reconciles it and retries the unpersisted track.

A normal Python exception from extraction is converted to a failed outcome as today. An
external `SIGKILL` cannot be intercepted, but all earlier committed outcomes survive.

## Verification

Tests must demonstrate observable behavior:

- Essentia adapters receive `float32` arrays without a full-track precision conversion;
- spectral values remain equivalent on representative and short inputs;
- spectral working storage does not grow with the number of frames;
- the first outcome is queryable from a separate SQLite connection before the next extraction
  completes;
- no more than `workers` extractions are simultaneously active;
- successful and failed counters and events remain compatible;
- a synthetic abandoned run is reconciled to `partial` or `failed`, and persisted successes
  are reused on the next run;
- focused tests, the complete test suite, Ruff, mypy, and the Docker analysis smoke pass.
