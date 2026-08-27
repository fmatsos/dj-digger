# Duplicates Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `duplicates` command that fingerprints audio, lists duplicate recordings, and marks the best-quality copy per source.

**Architecture:** Keep duplicate detection separate from the existing musical DSP pipeline. FFmpeg produces versioned Chromaprints in bounded child processes, SQLite stores current fingerprints and per-source quality selections, and duplicate groups are derived from equal fingerprints among present tracks.

**Tech Stack:** Python 3.12, Typer, SQLite, FFmpeg/FFprobe Chromaprint, Rich, pytest, Ruff, mypy.

---

## Public contract

```text
dj-digger duplicates --analyze [--mark-best-quality] [--source NAME]
                     [--workers N] [--track-timeout SECONDS] --config PATH

dj-digger duplicates --list [--source NAME] --config PATH

dj-digger duplicates --mark-best-quality [--source NAME] --config PATH
```

- `--analyze` and `--list` are mutually exclusive.
- `--mark-best-quality` is valid alone or with `--analyze`, never with `--list`.
- `--workers` and `--track-timeout` are valid only with `--analyze`; defaults remain `1` and `1800.0`.
- At least one action is required. Invalid combinations fail as Typer usage errors with exit code 2 before opening the catalog.
- `--source` accepts one enabled configured source and scopes every requested action. Without it, all enabled sources participate.
- Progress and diagnostics use `stderr`; the final compact JSON diagnostic uses `stdout`.
- A partial per-track analysis returns exit code 2; a command-level failure returns 1.

## Task 1: Introduce catalog schema v7 and a preserving v6 migration

**Files:**
- Create: `src/dj_digger/catalog/sql/catalog-v7.sql`
- Create: `src/dj_digger/catalog/sql/catalog-v6-to-v7.sql`
- Create: `schemas/catalog-v7.sql`
- Modify: `src/dj_digger/catalog/migrations.py`
- Test: `tests/test_catalog_migrations.py`

- [ ] Add failing migration tests proving that a populated v6 catalog upgrades to v7 without losing sources, tracks, metadata, or musical analysis rows; v7 reopening is idempotent; v1-v5 and unversioned non-empty catalogs remain rejected.
- [ ] Add schema-contract tests for these v7 additions:

```sql
ALTER TABLE technical_audio_metadata ADD COLUMN bit_depth INTEGER NULL;
ALTER TABLE technical_audio_metadata ADD COLUMN input_size_bytes INTEGER NULL;
ALTER TABLE technical_audio_metadata ADD COLUMN input_mtime_ns INTEGER NULL;

CREATE TABLE audio_fingerprints (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    fingerprint_hash TEXT NOT NULL,
    fingerprint_version TEXT NOT NULL,
    input_size_bytes INTEGER NOT NULL,
    input_mtime_ns INTEGER NOT NULL,
    fingerprinted_at TEXT NOT NULL
);

CREATE INDEX audio_fingerprints_group_idx
    ON audio_fingerprints(fingerprint_hash);

CREATE TABLE duplicate_quality_selections (
    source_id TEXT NOT NULL REFERENCES library_sources(source_id),
    fingerprint_hash TEXT NOT NULL,
    preferred_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    ranking_version TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    PRIMARY KEY (source_id, fingerprint_hash)
);
```

- [ ] Implement a transactionally applied v6-to-v7 upgrade. Fresh catalogs load `catalog-v7.sql`; current v7 catalogs are accepted unchanged.
- [ ] Keep `schemas/catalog-v7.sql` byte-identical to the packaged schema and update tests that currently name v6.
- [ ] Run `uv run --python 3.12 pytest tests/test_catalog_migrations.py -q` and expect all tests to pass.
- [ ] Commit the schema change alone with `feat: add duplicate catalog schema`.

## Task 2: Extract current technical quality facts

**Files:**
- Modify: `src/dj_digger/analysis/audio.py`
- Modify: `src/dj_digger/analysis/ffmpeg.py`
- Modify: `src/dj_digger/catalog/repositories.py`
- Test: `tests/test_ffmpeg.py`

- [ ] Extend `TechnicalAudioMetadata` with `bit_depth`, parsed from `bits_per_raw_sample` and then `bits_per_sample` when the first value is unavailable.
- [ ] Split the lightweight FFprobe facts from the existing full loudness measurement so duplicate analysis does not run `ebur128` over every file merely to rank quality.
- [ ] Add a repository operation that upserts technical facts with the track's current `size_bytes` and `mtime_ns` while preserving any existing loudness, true-peak, and dynamic-range measurements.
- [ ] Test 24-bit lossless, lossy bitrate, missing/malformed facts, freshness facts, and preservation of existing measurements.
- [ ] Run `uv run --python 3.12 pytest tests/test_ffmpeg.py -q` and expect all tests to pass.
- [ ] Commit with `feat: persist audio quality facts`.

## Task 3: Add bounded Chromaprint extraction

**Files:**
- Create: `src/dj_digger/duplicates/__init__.py`
- Create: `src/dj_digger/duplicates/fingerprint.py`
- Test: `tests/test_duplicate_fingerprint.py`

- [ ] Define a small extractor contract returning the complete base64 Chromaprint and its SHA-256 group identifier. Pin an explicit identity such as `ffmpeg-chromaprint/1` so algorithm changes invalidate stale rows.
- [ ] Invoke FFmpeg without a shell:

```python
[
    "ffmpeg", "-v", "error", "-i", str(path),
    "-map", "0:a:0", "-f", "chromaprint",
    "-algorithm", "1", "-fp_format", "base64", "-",
]
```

- [ ] Enforce the per-track timeout, reject non-zero exits and empty fingerprints with actionable errors, and never load decoded audio into the parent process.
- [ ] Test safe argv handling, stable hashing, timeout, malformed output, process failure, and identical fingerprints for WAV/FLAC/MP3 encodings of the same generated signal.
- [ ] Run `uv run --python 3.12 pytest tests/test_duplicate_fingerprint.py -q` and expect all tests to pass.
- [ ] Commit with `feat: extract chromaprint fingerprints`.

## Task 4: Persist fingerprints and derive duplicate groups

**Files:**
- Create: `src/dj_digger/duplicates/repository.py`
- Create: `src/dj_digger/duplicates/service.py`
- Test: `tests/test_duplicates_service.py`

- [ ] Add repository methods to select present tracks from enabled sources, reuse only fingerprints matching track size, mtime, and fingerprint version, upsert each successful result immediately, and query groups in deterministic order.
- [ ] Treat a group as duplicate only when at least two present tracks in the requested scope share the complete fingerprint hash. With `--source`, exclude members from other sources; without it, allow cross-source groups.
- [ ] Implement bounded scheduling with at most `workers` active FFmpeg children and hold a catalog advisory lock named `duplicates` across analysis/reconciliation.
- [ ] Continue after per-track failures. Return a result containing exactly these summary facts:

```python
files_total: int
analyzed: int
reused: int
failed: int
duplicate_files: int
duplicate_groups: int
elapsed_seconds: float
marked_best: int
```

- [ ] Invalidate a stored quality selection when a member's fingerprint or current technical facts cease to match the selection's inputs. Never include missing tracks.
- [ ] Test empty catalogs, source filtering, cross-source matches, stale reuse, partial failure, immediate persistence, deterministic ordering, worker bounds, timeout propagation, and lock contention.
- [ ] Run `uv run --python 3.12 pytest tests/test_duplicates_service.py -q` and expect all tests to pass.
- [ ] Commit with `feat: detect duplicate recordings`.

## Task 5: Select the best-quality copy per source

**Files:**
- Create: `src/dj_digger/duplicates/quality.py`
- Modify: `src/dj_digger/duplicates/service.py`
- Test: `tests/test_duplicate_quality.py`

- [ ] Implement a versioned deterministic ranking with these priorities:
  1. known lossless, then known lossy, then unknown;
  2. for lossless files: bit depth, then sample rate;
  3. for lossy files: bitrate, then sample rate;
  4. relative path ascending as the final tie-breaker.
- [ ] Elect one winner per `(source_id, fingerprint_hash)`, even when an unfiltered list contains a cross-source group.
- [ ] Before standalone marking, verify that every present track in the requested scope has a current fingerprint and current quality facts. On failure, return status `failed` with the count and identities of tracks requiring analysis, without changing selections.
- [ ] Replace all selections for the requested source set atomically. When combined with `--analyze`, mark only after analysis completes and do not mark an incomplete/partial scope.
- [ ] Test every ranking tier, unknown values, deterministic ties, independent source winners, completeness refusal, and atomic rollback.
- [ ] Run `uv run --python 3.12 pytest tests/test_duplicate_quality.py -q` and expect all tests to pass.
- [ ] Commit with `feat: mark best duplicate quality`.

## Task 6: Expose the `duplicates` CLI command

**Files:**
- Modify: `src/dj_digger/cli.py`
- Modify: `src/dj_digger/application.py`
- Create: `tests/test_cli_duplicates.py`
- Modify: `tests/test_cli.py`

- [ ] Add application methods that validate enabled sources and delegate analyze, list, and mark operations to the duplicate service.
- [ ] Add the Typer command with annotated boolean options and reuse `PositiveWorkersOption`, `TrackTimeoutOption`, `RichProgressReporter`, and `_run`.
- [ ] Validate the complete option matrix before constructing `WorkspaceApplication`. In particular, reject no action, analyze+list, list+mark, and execution controls without analyze.
- [ ] Emit list JSON as ordered groups containing `group_id` and member objects with source, track ID, relative path, technical facts, and `best_quality` state.
- [ ] Ensure analysis JSON includes the required counters and elapsed time, while `_run` continues to map `failed` to exit 1 and `partial` to exit 2.
- [ ] Test help output, all valid and invalid combinations, source propagation, execution defaults, unknown/disabled sources, JSON structure, stderr/stdout separation, and exit codes.
- [ ] Run `uv run --python 3.12 pytest tests/test_cli.py tests/test_cli_duplicates.py -q` and expect all tests to pass.
- [ ] Commit with `feat: add duplicates command`.

## Task 7: Publish duplicate state in `tracks.tsv`

**Files:**
- Modify: `src/dj_digger/catalog/repositories.py`
- Modify: `src/dj_digger/exports/tracks.py`
- Modify: `schemas/tracks.schema.json`
- Modify: `tests/test_tracks_export.py`

- [ ] Extend the canonical inventory with nullable `duplicate_group_id` and `duplicate_best_quality` columns.
- [ ] Export the group identifier only when the present track belongs to a group of at least two present tracks. Export `true` for the per-source winner, `false` for other members of a marked group, and an empty value for non-duplicates or unmarked groups.
- [ ] Preserve stable row ordering and atomic publication; update the packaged schema inclusion only if the existing package glob does not already include the modified file.
- [ ] Test all three quality states, cross-source groups, source-specific winners, missing members, schema validation, and snapshot compatibility.
- [ ] Run `uv run --python 3.12 pytest tests/test_tracks_export.py tests/test_snapshot.py -q` and expect all tests to pass.
- [ ] Commit with `feat: export duplicate quality markers`.

## Task 8: Documentation and final verification

**Files:**
- Modify: `README.md`
- Modify only if required by existing assertions: `tests/test_requalification_documentation.py`

- [ ] Document command examples, option compatibility, source scoping, conservative exact-Chromaprint grouping, quality ranking, JSON output, exit codes, and the requirement that FFmpeg provide its Chromaprint muxer.
- [ ] Extend `doctor` to report a missing FFmpeg/FFprobe binary or unavailable Chromaprint muxer when duplicate analysis is expected; do not make Essentia a dependency of `duplicates`.
- [ ] Run the focused duplicate, CLI, migration, export, doctor, and documentation tests.
- [ ] Run the complete verification suite:

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uv run --python 3.12 --extra analysis pytest -q
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx ruff check src tests
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx --with typer mypy src
git diff --check
```

- [ ] Run a temporary-library smoke test that scans generated WAV/FLAC/MP3 copies, analyzes duplicates, marks quality, lists the group, and exports `tracks.tsv`, without writing to source audio files.
- [ ] Review the final diff for unrelated files and commit documentation/verification changes with `docs: document duplicate management`.

## Acceptance criteria

- The three requested actions and `--source` obey the validated composition rules.
- A same-recording WAV/FLAC/MP3 set is grouped; distinct audio and edits are not deliberately similarity-matched.
- Interrupted or partial work is reusable and never corrupts the catalog.
- Standalone marking cannot run on an incompletely analyzed scope.
- Exactly one best-quality track is selected per duplicate group and source.
- `tracks.tsv` exposes stable group and quality-selection state.
- Existing v6 catalogs upgrade without losing data, while unsupported older catalogs remain rejected.
- All tests, Ruff, strict mypy, package/schema checks, and the FFmpeg smoke test pass under Python 3.12.
