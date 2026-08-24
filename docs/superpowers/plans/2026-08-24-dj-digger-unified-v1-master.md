# DJ Digger Unified V1A/V1B Implementation Plan — Master

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `export-music-audit.sh` and the planned standalone `dj-audio-analyzer` with one `dj-digger` product whose persistent SQLite catalog is canonical, whose exports are regenerable facets, and whose set curator migrates to `tracks.tsv` in V1B.

**Architecture:** One workspace owns one SQLite database and N configured library sources. Scanning, metadata extraction, technical/DSP analysis, artifact discovery, audit exports and set-curation contracts are isolated subsystems inside one product; files never feed state back into DJ Digger. V1A preserves compatibility facets while V1B migrates every first-party inventory consumer to `tracks.tsv`.

**Tech Stack:** Python 3.12; SQLite; Typer; FFmpeg; ExifTool; Essentia 2.1b6.dev1438; librosa 1.0.0; NumPy 2.5.1; SciPy 1.18.0; jsonschema 4.26.0; pytest 9.1.1; Ruff 0.16.3; mypy 2.3.1; Docker/Compose; JSON Schema Draft 2020-12.

**Spec:** `docs/superpowers/specs/2026-08-24-dj-digger-unified-v1-design.md`

## Global Constraints

- SQLite is the only canonical persistent state; exports are projections and never DJ Digger inputs.
- One workspace database aggregates N sources identified by stable `source_id` values.
- Source libraries are strictly read-only.
- Track identity is internal `track_id`; public location is `(source_id, path)` where `path` is source-relative.
- Missing reconciliation is authorized only by a complete successful source scan.
- Missing tracks, metadata, analysis and lifecycle events are retained historically.
- V1 does not fingerprint audio and does not infer move/rename or duplicates.
- `tracks.tsv` exists in V1A, contains only `present` tracks by default, and is the supported first-party inventory contract in V1B.
- V1A preserves `djing-files.tsv`/`music-files.tsv` and the historical audit facets as compatibility projections.
- Analysis schema version is `2`; set schema version is `2`; catalog schema version is `1`; tracks export schema version is `1`.
- Structured publication is validated and atomic.
- `copy-set.sh` remains external and consumes generated M3U8 paths; DJ Digger never executes it automatically.

---

## Workstream order

1. `2026-08-24-dj-digger-catalog-v1a.md` — product bootstrap, canonical SQLite, scanner, metadata, artifacts, exports, snapshots and CLI.
2. `2026-08-24-dj-digger-analysis-v1a.md` — integrate technical/DSP analysis into the catalog and publish source-aware analysis facets.
3. `2026-08-24-electronic-dj-set-curator-v1a-v1b.md` — keep V1A compatibility, then migrate availability and set identity to `tracks.tsv`.
4. `2026-08-24-dj-digger-integration-v1a-v1b.md` — parity, failure semantics, real-library pilot, V1B cut-over and regression acceptance.

Workstreams 1 and 2 are sequential at their persistence boundary: analysis depends on catalog identities. Curator text can be prepared in parallel, but V1B cut-over cannot merge before `tracks.tsv` and source-aware analysis fixtures are stable.

## Milestones

### Milestone A — canonical catalog

Exit conditions:

```text
successful scan => present/missing/restored lifecycle is correct
failed scan => zero missing transitions
source root relocation => same (source_id, relative_path) identities
empty directories and DJ artifacts are cataloged from the same traversal
```

### Milestone B — V1A export coexistence

Exit conditions:

```text
tracks.tsv validates against tracks.schema.json
legacy djing-files.tsv is path-for-path compatible
historical directory/statistics/metadata/artifact facets are catalog-derived
snapshot --archive creates a self-describing .tar.gz
```

### Milestone C — catalog-backed audio analysis

Exit conditions:

```text
unchanged track + same analysis identity => reused
changed size/mtime => reanalyzed
missing track => historical analysis retained
restored unchanged track => reusable analysis allowed
all analysis artifacts validate with source_id + track_id
```

### Milestone D — V1B consumer migration

Exit conditions:

```text
no first-party code requires djing-files.tsv or music-files.tsv
set selection requires set_eligible=true in tracks.tsv
set JSON records source_id + track_id per track
M3U8 paths remain compatible with copy-set.sh
legacy inventory facets can be disabled without first-party failures
```

### Milestone E — real-library regression

Run the known Acid Rave set case plus a representative subset containing compatible blends, low-end conflicts, low-confidence analysis, empty directories, DJ metadata artifacts and at least one intentionally missing/restored track.

## Branch/review policy

Recommended branch sequence:

```text
feature/dj-digger-catalog-v1a
feature/dj-digger-analysis-v1a
feature/dj-digger-curator-v1b
feature/dj-digger-integration-v1b
```

Every task in sub-plans ends in a focused commit and must pass its local tests before review. No schema contract is changed during calibration without first updating the approved spec and schema bundle.
