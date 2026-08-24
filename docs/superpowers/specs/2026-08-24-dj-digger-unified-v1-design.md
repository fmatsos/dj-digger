# DJ Digger — Unified Library Catalog, Audio Analysis and Electronic Set Curator V1

Date: 2026-08-24  
Status: Approved  
Supersedes: `2026-08-24-dj-digger-electronic-dj-set-curator-v1-design.md`

## 1. Goal

DJ Digger is the single tool responsible for discovering, cataloging, inspecting, analyzing and exporting the user's music libraries for DJ set construction.

It absorbs the full functional coverage of the historical `export-music-audit.sh` utility and the planned `dj-audio-analyzer` product. There must be no second canonical inventory generator and no export file used as an internal source of truth.

The end-to-end V1 workflow is:

```text
configured library sources
        │
        ▼
filesystem scan ──► persistent SQLite catalog
        │                   │
        │                   ├── embedded metadata (ExifTool)
        │                   ├── technical audio facts (FFmpeg)
        │                   ├── musical/DSP analysis
        │                   ├── structural sections
        │                   ├── DJ application artifacts
        │                   └── historical events / runs
        │
        ▼
regenerable export facets
        │
        ├── tracks.tsv                    canonical public inventory export
        ├── dj-analysis.tsv               track-level DSP facts
        ├── dj-sections.jsonl             section-level DSP facts
        ├── dj-analysis-run.json          analysis audit
        ├── library-artifacts.tsv         discovered DJ metadata/artifacts
        ├── directory/statistics facets   audit/navigation projections
        └── V1A legacy compatibility facets
                ├── djing-files.tsv
                └── music-files.tsv

export facets ──► electronic-dj-set-curator skill ──► set artifacts
```

The first use case remains electronic DJ set construction where beatmix quality, structure and low-end continuity are first-class constraints.

---

## 2. Architectural invariants

### 2.1 SQLite is canonical

A single persistent SQLite database is the authoritative state of one DJ Digger workspace.

TSV, CSV, JSON, JSONL and text files are projections of this database. They are never authoritative inputs to DJ Digger itself and must be reproducible from SQLite plus the current configuration.

An export may be deleted and regenerated without losing information.

### 2.2 One workspace, N sources

One database may aggregate any number of configured library sources.

A source has a stable `source_id` independent of its filesystem mount path.

Example:

```toml
[workspace]
database = "./dj-digger.sqlite"
exports = "./exports"

[[library.sources]]
id = "djing"
path = "/mnt/tank/djing"
set_eligible = true
analyze = true

[[library.sources]]
id = "music"
path = "/mnt/tank/music"
set_eligible = false
analyze = false
```

Changing a source root from `/mnt/tank/djing` to `/srv/music/djing` must not create new logical tracks when relative paths remain unchanged.

### 2.3 Source libraries are immutable

DJ Digger is read-only with respect to configured media libraries.

It must never modify, move, rename, delete or retag an audio file. Generated state, logs, databases and exports must live outside source roots.

### 2.4 Historical catalog, not disposable mirror

The catalog retains tracks that disappear from the filesystem.

A track has a lifecycle including at least:

```text
discovered_at
last_seen_at
presence_status = present | missing
missing_since
last_restored_at
```

Missing tracks remain queryable and keep previous metadata and analysis results.

### 2.5 Missing detection is commit-on-success

A track may transition from `present` to `missing` only after a complete successful scan of its source.

If the source is unavailable, unreadable, partially scanned, interrupted or otherwise fails validation:

- the scan run is marked failed;
- observations already made may be retained as run diagnostics, but must not be used to declare unseen files missing;
- no existing presence state is invalidated for that source.

This rule prevents a temporarily unmounted filesystem from making an entire library appear deleted.

### 2.6 Stable logical identity is independent of absolute path

V1 logical identity is based on an internal immutable `track_id` and a source-scoped path mapping.

The public location tuple is:

```text
(source_id, relative_path)
```

`absolute_path` is derived from the current source root and relative path. It is useful to local consumers but is not persistent identity.

V1 does not attempt to infer that two different paths represent the same audio content.

### 2.7 Facts before semantics

Filesystem facts, embedded tags, technical audio properties and DSP facts have distinct ownership. A value must have one authoritative producer.

Semantic labels are optional derivatives and never override factual measurements.

### 2.8 Exports are consumer contracts

Exports remain important even though they are not canonical storage.

The ChatGPT skill and set-copy workflow consume filesystem paths from exports. Path fidelity is therefore part of the public contract, not an implementation detail.

---

## 3. Repository and product boundary

V1 is one product: `dj-digger`.

The previous standalone `dj-audio-analyzer` product boundary is removed. Audio analysis becomes an internal subsystem of DJ Digger.

Suggested layout:

```text
dj-digger/
├── pyproject.toml
├── Dockerfile
├── compose.yaml
├── config/
│   ├── dj-digger.example.toml
│   └── analysis.toml
├── schemas/
│   ├── tracks.schema.json
│   ├── library-artifacts.schema.json
│   ├── dj-analysis.schema.json
│   ├── dj-sections.schema.json
│   ├── dj-analysis-run.schema.json
│   └── dj-set.schema.json
├── src/dj_digger/
│   ├── cli.py
│   ├── config.py
│   ├── catalog/
│   │   ├── database.py
│   │   ├── migrations.py
│   │   ├── repositories.py
│   │   └── models.py
│   ├── scanning/
│   │   ├── scanner.py
│   │   ├── classifiers.py
│   │   └── lifecycle.py
│   ├── metadata/
│   │   └── exiftool.py
│   ├── analysis/
│   │   ├── ffmpeg.py
│   │   ├── rhythm.py
│   │   ├── spectrum.py
│   │   ├── segmentation.py
│   │   ├── semantics.py
│   │   └── pipeline.py
│   ├── artifacts/
│   │   └── discovery.py
│   └── exports/
│       ├── tracks.py
│       ├── analysis.py
│       ├── audit.py
│       └── legacy.py
└── tests/
```

Boundaries are logical; exact modules may change during implementation if tests expose a simpler decomposition.

---

## 4. Canonical database model

### 4.1 `library_sources`

Stores configured sources without making their current absolute root part of track identity.

Core fields:

```text
source_id           TEXT PRIMARY KEY
root_path           TEXT NOT NULL
set_eligible        BOOLEAN NOT NULL
analyze             BOOLEAN NOT NULL
enabled             BOOLEAN NOT NULL
created_at          DATETIME NOT NULL
updated_at          DATETIME NOT NULL
last_successful_scan_id INTEGER NULL
```

### 4.2 `tracks`

One logical catalog record per currently known source/path identity in V1.

Core fields:

```text
id                  INTEGER PRIMARY KEY
source_id           TEXT NOT NULL REFERENCES library_sources(source_id)
relative_path       TEXT NOT NULL
filename            TEXT NOT NULL
extension           TEXT NOT NULL
size_bytes          INTEGER NOT NULL
mtime_ns            INTEGER NOT NULL
presence_status     TEXT NOT NULL CHECK (... present/missing ...)
discovered_at       DATETIME NOT NULL
last_seen_at        DATETIME NOT NULL
missing_since       DATETIME NULL
last_restored_at    DATETIME NULL
created_scan_id     INTEGER NOT NULL
last_seen_scan_id   INTEGER NOT NULL
UNIQUE(source_id, relative_path)
```

`mtime_ns` or another lossless filesystem timestamp representation is stored internally. Human-readable timestamps may be exported separately.

### 4.3 `directories`

Stores directory observations from the same source traversal, including empty directories. This is required to preserve the historical complete directory inventory without performing a second filesystem walk during export.

Core fields:

```text
id                  INTEGER PRIMARY KEY
source_id           TEXT NOT NULL REFERENCES library_sources(source_id)
relative_path       TEXT NOT NULL
presence_status     TEXT NOT NULL
discovered_at       DATETIME NOT NULL
last_seen_at        DATETIME NOT NULL
missing_since       DATETIME NULL
last_seen_scan_id   INTEGER NOT NULL
UNIQUE(source_id, relative_path)
```

Directories follow the same positive-observation / successful-scan reconciliation rule as tracks.

### 4.4 `embedded_metadata`

ExifTool-owned tags and only ExifTool-owned tags.

At minimum V1 preserves the historical audit coverage:

```text
title
artist
album_artist
album
track_number
disc_number
genre
date
year
composer
comment
tag_bpm
tag_initial_key
grouping
metadata_extracted_at
extractor_version
```

The raw ExifTool payload may optionally be retained for diagnostics, but public normalized fields remain explicit.

### 4.5 `technical_audio_metadata`

FFmpeg-owned technical media facts:

```text
duration_seconds
sample_rate
channels
codec
container
bitrate
lossless
loudness_lufs
true_peak_db
dynamic_range
probe_version
probed_at
```

Fields previously exported by ExifTool that overlap with FFmpeg technical facts are normalized here and have FFmpeg as the canonical technical producer.

### 4.6 `audio_analysis`

Versioned track-level DSP results.

A result is identified by the track plus the analysis identity:

```text
track_id
analysis_schema_version
analyzer_version
config_hash
input_size_bytes
input_mtime_ns
analysis_status
analysis_confidence
...
```

The remaining factual fields preserve the existing V1 `dj-analysis.tsv` design, including BPM, beat stability, key, spectral/low-end properties and 8/16/32/64-bar intro/outro windows.

Old analyses do not need to be destroyed when a new algorithm/configuration is introduced. The latest applicable successful result is the active projection.

### 4.7 `track_sections`

Stores structural section analysis for a particular versioned analysis result.

Facts, deterministic derived flags and optional confidence-gated semantic labels remain separated.

### 4.8 `library_artifacts`

Catalogs non-audio DJ/library artifacts found during the same source traversal.

V1 must preserve discovery coverage from `export-music-audit.sh`, including:

```text
Traktor:     *.nml, *.tsi, collection.nml
Playlists:   *.m3u, *.m3u8, *.pls
Cue:         *.cue
Generic:     *.xml
Databases:   *.db, *.sqlite, *.sqlite3, database, "database V2"
Serato:      *.crate, *.scrate, *.session, all relevant content under _Serato_
```

Fields:

```text
source_id
relative_path
artifact_type
size_bytes
mtime_ns
present
first_seen_at
last_seen_at
missing_since
```

Dedicated Serato/Traktor export facets may be generated as filtered views rather than through additional filesystem scans.

### 4.9 `scan_runs`

One row per attempted source scan.

```text
id
source_id
started_at
finished_at
status = running | succeeded | failed
files_seen
audio_seen
artifacts_seen
error_stage
error_message
scanner_version
```

A successful run is the unit that authorizes missing-file reconciliation.

### 4.10 `analysis_runs`

Audit of requested audio-analysis work:

```text
id
started_at
finished_at
status
eligible
analyzed
reused
failed
analysis_schema_version
analyzer_version
config_hash
```

Per-track failures are retained without aborting unrelated analysis work.

### 4.11 `track_events`

Append-only significant lifecycle events, not one snapshot per scan.

Initial V1 event types:

```text
discovered
missing
restored
filesystem_metadata_changed
embedded_metadata_changed
analysis_completed
analysis_failed
```

Suggested fields:

```text
id
track_id
occurred_at
scan_run_id NULL
analysis_run_id NULL
event_type
payload_json NULL
```

V2 may add `moved` and duplicate/fingerprint-related events.

---

## 5. Scanning and reconciliation

### 5.1 One traversal per source

A source scan should traverse the filesystem once and classify entries as it goes.

The scanner collects:

- audio inventory;
- every directory, including empty directories;
- supported DJ application metadata/artifacts.

Entries below `_Serato_` are classified as Serato artifacts even when their extension is not otherwise listed.

It must not reproduce the historical pattern of independent recursive scans for inventory, directory trees, Serato, Traktor and generic metadata discovery.

### 5.2 Source validation before scan

Before traversal:

- source root must resolve and be a directory;
- workspace database/output must not be inside the immutable source root;
- source must be readable;
- source configuration must be internally valid.

Failure here creates a failed `scan_run` and changes no presence state.

### 5.3 Observation phase

During traversal, each supported audio file upserts its filesystem facts and updates `last_seen_at` for the current run.

New paths generate `discovered` events.

Previously missing paths observed again generate `restored` events and clear `missing_since`.

Changed `size_bytes` or `mtime_ns` generate `filesystem_metadata_changed` and invalidate dependent metadata/analysis eligibility as required.

### 5.4 Reconciliation phase

Only after traversal and scan validations succeed:

1. mark the run `succeeded`;
2. find previously `present` tracks/artifacts in this source not observed by the run;
3. mark them `missing`;
4. set `missing_since` once;
5. append corresponding events;
6. update `last_successful_scan_id`.

This final reconciliation is transactional.

### 5.5 Failed scans

A failed scan never runs missing reconciliation.

Previously observed `present` rows stay present even if not reached before failure.

The failed run remains visible for diagnostics and future dashboard use.

---

## 6. Metadata and analysis pipeline

### 6.1 Embedded metadata extraction

ExifTool is used only for files requiring metadata refresh.

A refresh is required when:

- the track is newly discovered;
- relevant filesystem identity changed (`size_bytes` and/or `mtime_ns`);
- extractor version or normalization schema requires re-extraction;
- explicit force/rebuild is requested.

ExifTool failures are recorded per track and do not make the scan itself fail once filesystem discovery has succeeded.

### 6.2 Audio analysis eligibility

A track is analyzed when:

- its source is enabled with `analyze = true`;
- it is `present`;
- its format is supported;
- no active analysis exists for the exact analysis identity and current file facts.

### 6.3 Incrementality without a separate cache abstraction

There is no destructive `AnalysisCache.prune()` model.

The catalog itself answers whether reusable analysis exists.

Conceptually:

```text
active analysis exists where
    track_id = current track
    input_size_bytes = tracks.size_bytes
    input_mtime_ns = tracks.mtime_ns
    analysis_schema_version = requested schema
    analyzer_version = requested analyzer
    config_hash = requested config
    analysis_status is reusable
```

If such a result exists, the pipeline reuses it.

### 6.4 Per-track resilience

A corrupt or unsupported file must not abort analysis of other tracks.

Failures retain:

```text
track_id
stage
error class/message
analysis identity
occurred_at
```

### 6.5 Existing DSP requirements retained

The existing V1 audio-analysis requirements remain in scope:

- FFmpeg decoding/probing;
- Essentia rhythm/BPM/key extraction;
- NumPy/SciPy spectral facts;
- librosa-compatible structural segmentation;
- 8/16/32/64-bar stable intro/outro windows;
- kick/bass/sub/low/low-mid facts;
- onset and spectral measurements;
- deterministic derived flags;
- optional semantic section labels with confidence threshold `>= 0.80` by default;
- explainable transition suitability.

---

## 7. Export architecture

### 7.1 General rules

Exports are generated from SQLite, written atomically, and validated before publication.

Unless a facet explicitly represents history, user-facing current-library exports include only tracks/artifacts with `presence_status = present`.

This makes membership in the canonical current inventory equivalent to physical availability at the last successful scan.

### 7.2 `tracks.tsv` — canonical public inventory facet

`tracks.tsv` exists in V1A and becomes the only supported inventory contract for consumers in V1B.

It is a global N-source export. By default it contains only `present` tracks.

Required identity/location columns:

```text
source_id
path
absolute_path
filename
extension
size_bytes
mtime
set_eligible
```

`path` is the exact path relative to the configured source root.

`absolute_path` is derived at export time from current source configuration and `path`.

Additional normalized columns include useful embedded metadata and technical facts, for example:

```text
title
artist
album_artist
album
genre
tag_bpm
tag_initial_key
duration_seconds
sample_rate
codec
container
bitrate
lossless
```

The exact V1 column set and order must be frozen by a versioned tabular schema before implementation.

Canonical serialization rules:

```text
extension   lowercase filesystem suffix including the leading dot (e.g. .flac)
mtime       ISO-8601 local timestamp with second precision for human/export compatibility
```

SQLite retains `mtime_ns` for lossless incremental identity; the TSV representation is not used as the incremental cache key.

### 7.3 Path fidelity contract

For every `tracks.tsv` row:

```text
path == exact library-relative path usable by playlist/set tooling
```

No normalization may change case, Unicode spelling, directory separators in the serialized contract, or selected audio version in a way that breaks filesystem resolution on the target host.

Set M3U8 files continue to contain exact source-relative paths.

The set-copy script remains responsible for resolving those relative paths against its explicit `--library` source root.

A generated set must not silently combine tracks from incompatible library roots. The set artifact must therefore preserve `source_id` for validation even if M3U8 remains path-only for compatibility.

### 7.4 Analysis facets

Retain:

```text
dj-analysis.tsv
dj-sections.jsonl
dj-analysis-run.json
```

Their internal source association must become unambiguous for N-source workspaces. Schemas must add `source_id` and preferably stable `track_id` where machine-to-machine joining benefits from it.

`path` remains present for human inspection and skill consumption.

### 7.5 Audit/navigation facets inherited from `export-music-audit`

The historical audit coverage is preserved, but generated from catalog data:

```text
<source>-directories.txt
<source>-tree-depth-3.txt
<source>-directory-stats.tsv
<source>-summary.txt
library-artifacts.tsv
serato-directories.txt
traktor-files.tsv
README.txt or equivalent export manifest
audit/run logs
```

Directory and summary facets must not trigger new filesystem traversals.

### 7.6 V1A legacy compatibility facets

During V1A, generate:

```text
djing-files.tsv
music-files.tsv
```

when corresponding source IDs exist, preserving the historical five-column contract:

```text
path
filename
extension
size_bytes
mtime
```

For these compatibility facets, `extension` keeps the leading dot and `mtime` keeps the historical ISO second-precision representation.

V1A also preserves the remaining historical source-specific audit outputs as generated projections:

```text
djing-metadata.csv
music-metadata.csv
djing-directories.txt
music-directories.txt
djing-tree-depth-3.txt
music-tree-depth-3.txt
djing-directory-stats.tsv
music-directory-stats.tsv
djing-summary.txt
music-summary.txt
dj-metadata-files.tsv
serato-directories.txt
traktor-files.tsv
README.txt
```

The metadata CSV facets are regenerated from normalized catalog/metadata state rather than acting as ExifTool intermediate state. Their compatibility schema must preserve the useful historical columns.

These facets are explicitly compatibility/audit outputs, not canonical data.

### 7.7 V1B migration

V1B migrates all first-party consumers from legacy source-specific inventories to `tracks.tsv`.

Mandatory migrations:

- `electronic-dj-set-curator` project instructions;
- `electronic-dj-set-curator` skill workflow;
- exact-path availability validation;
- test fixtures and validators;
- integration/pilot inventory generation;
- examples and operator documentation;
- any DJ Digger helper consuming `djing-files.tsv`.

The set-copy script consumes generated M3U8 and therefore does not need to parse `tracks.tsv`; however, DJ Digger/skill path generation must remain compatible with it.

At V1B completion:

```text
tracks.tsv = supported inventory contract
djing-files.tsv / music-files.tsv = deprecated compatibility facets
```

Legacy facets may be removed in a later release only after confirming no external workflow still consumes them.

### 7.8 Snapshot/archive export

The historical audit command always produced a timestamped directory and `.tar.gz` archive. DJ Digger must preserve this capability as an explicit snapshot operation.

A snapshot contains a self-describing export bundle generated from one consistent database view:

```text
snapshot manifest
configured-source summary
tracks.tsv
configured analysis facets
configured audit/navigation facets
legacy compatibility facets when enabled
run diagnostics
schema/version identifiers
```

The archive is a packaging artifact only. Restoring or importing a snapshot does not replace SQLite automatically.

---

## 8. CLI

### 8.1 Primary workflow

Normal operation:

```bash
dj-digger refresh --config ./dj-digger.toml
```

`refresh` orchestrates:

```text
scan configured sources
→ reconcile successful scans
→ refresh embedded metadata
→ refresh eligible technical/DSP analysis
→ export configured facets
→ validate publication
```

A failure policy must distinguish source-scan integrity failures from per-track metadata/audio failures.

### 8.2 Operational primitives

Expose focused commands for diagnostics, automation and partial reruns:

```bash
dj-digger scan [--source ID]
dj-digger metadata [--source ID] [--path PREFIX] [--force]
dj-digger analyze [--source ID] [--path PREFIX] [--limit N] [--force] [--workers N]
dj-digger export [--facet NAME]
dj-digger snapshot [--output DIR] [--archive]
dj-digger doctor
dj-digger status
```

These are subcommands of one product, not separately deployed tools.

### 8.3 Removed concepts

The new CLI does not require:

```text
--inventory /path/to/djing-files.tsv
--no-prune
```

There is no external inventory authority and no destructive cache pruning mode.

---

## 9. Electronic DJ set curator integration

### 9.1 V1A

The skill may continue consuming `djing-files.tsv` while the new catalog and `tracks.tsv` are proven in parallel.

Analysis artifacts remain consumed as before, with schema migrations for `source_id` where required.

### 9.2 V1B

Project instructions change to:

```text
- tracks.tsv: canonical exported source of currently available local tracks.
- dj-analysis.tsv: canonical precomputed track-level audio-analysis facet.
- dj-sections.jsonl: canonical section-analysis facet.
- dj-analysis-run.json: analysis-run audit information.
```

Every selected track must resolve to a `present`, `set_eligible = true` `tracks.tsv` row.

Availability must never be inferred from model knowledge, directory names, web research or old set files.

### 9.3 Multi-source set semantics

For V1, a generated M3U8 intended for the existing copy workflow should normally target one `source_id` unless the caller explicitly supplies a library root capable of resolving all emitted paths.

Machine-readable `.set.json` records `source_id` per selected track.

The skill must fail validation rather than emit an ambiguous path when identical relative paths exist in multiple eligible sources.

### 9.4 Existing set-curation requirements retained

The existing transition engine, hard constraints, narrative trajectory, beam-search playlist construction, improvisation branches, transition sheet and `.set.json` audit remain in scope unchanged unless a schema migration is required by the new track identity model.

---

## 10. Schema/versioning policy

SQLite schema and public export schemas are versioned independently.

Recommended concepts:

```text
catalog_schema_version
tracks_export_schema_version
analysis_schema_version
analyzer_version
config_hash
```

Rules:

- database migrations are explicit, ordered and transactional;
- changing a public required column/name/serialization increments its export schema version;
- analyzer behavior change without analysis contract change increments `analyzer_version`;
- threshold/weight changes modify `config_hash`;
- unsupported public schema versions are rejected by first-party consumers;
- publication is atomic: an invalid new export must not replace the previous valid export.

---

## 11. Functional coverage matrix

The unified product must preserve all meaningful behavior from both predecessors.

| Existing capability | Unified owner | V1 result |
|---|---|---|
| Audio file discovery | Scanner/catalog | Preserved, generalized to N sources |
| File path/name/ext/size/mtime inventory | Catalog + `tracks.tsv` | Preserved |
| Directory list | Export projection | Preserved |
| Depth-3 tree | Export projection | Preserved |
| Level-1/2 directory counts | Export projection | Preserved |
| File count/bytes/GiB/ext summary | Export projection | Preserved |
| ExifTool embedded tags | Metadata subsystem | Preserved and normalized |
| Metadata completeness/audit | Run validation | Preserved without CSV-as-state |
| Traktor discovery | Artifact scanner/view | Preserved |
| Serato discovery | Artifact scanner/view | Preserved |
| M3U/M3U8/PLS/CUE/XML/DB discovery | Artifact scanner/view | Preserved |
| Read-only media guarantee | Product invariant | Preserved |
| Execution diagnostics | Run/event/log model | Preserved and expanded |
| Timestamped audit directory + tar.gz archive | Snapshot exporter | Preserved as explicit capability |
| Incremental audio analysis | Catalog-backed analysis lookup | Preserved |
| SQLite cache | Replaced by canonical SQLite model | Superseded |
| Cache pruning | Historical presence lifecycle | Removed intentionally |
| FFmpeg/Essentia/DSP analysis | Analysis subsystem | Preserved |
| Structural sections | Analysis subsystem | Preserved |
| Schema-validated analysis exports | Export subsystem | Preserved |
| Set-curator skill | ChatGPT integration | Preserved |
| Exact path verification | `tracks.tsv` V1B | Preserved/migrated |

---

## 12. Failure semantics

### 12.1 Source-level hard failure

Examples:

```text
root unavailable
permission/traversal failure preventing complete scan
catalog transaction failure
```

Result:

- scan status `failed`;
- no missing reconciliation;
- refresh reports degraded/failed status for that source;
- the previously published export bundle remains untouched;
- a normal `refresh` must not publish a new canonical `tracks.tsv` bundle if a required/set-eligible source failed its scan;
- diagnostic/stale exports, if explicitly requested, must be marked with source freshness in the manifest.

### 12.2 Track-level soft failure

Examples:

```text
ExifTool cannot parse tags
FFmpeg cannot decode
Essentia analysis fails
semantic segmentation fails
```

Result:

- track remains `present` if scan saw it;
- failure is recorded;
- independent tracks continue;
- exports surface `partial`/`failed` analysis status where appropriate.

### 12.3 Export failure

If a generated facet fails schema/consistency validation, it is not published over the previous valid facet.

---

## 13. Testing and acceptance

### 13.1 Scanner/catalog tests

Must prove:

- discovery of supported audio formats;
- exact relative-path preservation;
- N-source isolation;
- source-root relocation does not change source-relative identity;
- a successful scan marks unseen previous tracks missing;
- a failed/partial scan marks none missing;
- a missing track reappearing becomes restored;
- history/events survive later scans;
- source libraries are never opened for write.

### 13.2 Export tests

Must prove:

- `tracks.tsv` contains only `present` tracks by default;
- exact frozen header/order/serialization;
- `absolute_path` derives from current source configuration;
- V1A legacy `djing-files.tsv` exactly preserves its five-column contract;
- directory/statistics facets match SQL-derived catalog state;
- artifact views reproduce historical Traktor/Serato/general discovery semantics;
- invalid exports never replace last valid files.

### 13.3 Metadata/analysis tests

Retain existing deterministic DSP fixtures and regression tests, adapted to catalog-backed identity.

Must additionally prove:

- unchanged tracks reuse existing matching analysis;
- changed track facts trigger only necessary refresh/reanalysis;
- historical analysis is not deleted merely because a track is missing;
- a restored unchanged file may reuse analysis only when file facts and analysis identity still match;
- per-track errors do not abort unrelated work.

### 13.4 V1A integration acceptance

A representative real-library run must demonstrate:

- catalog import/discovery covers the same audio files as the historical exporter;
- legacy `djing-files.tsv` generated from SQLite is path-for-path compatible with the historical output modulo explicitly documented serialization normalization;
- `tracks.tsv` and legacy facets are internally consistent;
- analysis and set generation still work.

### 13.5 V1B integration acceptance

V1B is complete when:

- no first-party skill/project/test/integration code requires `djing-files.tsv` or `music-files.tsv`;
- all set candidates are resolved through `tracks.tsv`;
- generated M3U8 paths remain accepted by the set-copy workflow;
- regression generation of a known electronic set succeeds with exact-path validation;
- legacy facets can be disabled without breaking first-party workflows.

---

## 14. V1A / V1B delivery split

### V1A — unified catalog and coexistence

Deliver:

- one `dj-digger` product;
- persistent canonical SQLite database;
- N-source configuration;
- historical `present/missing/restored` lifecycle;
- safe source-scoped scan reconciliation;
- single-traversal inventory/artifact discovery;
- normalized ExifTool metadata;
- existing technical/DSP analysis pipeline integrated into the catalog;
- canonical `tracks.tsv`;
- existing analysis facets;
- audit/navigation facets replacing `export-music-audit.sh` coverage, including empty directories;
- source-specific legacy inventory and metadata facets for compatibility;
- deterministic timestamped snapshot directory and `.tar.gz` packaging capability;
- old external `export-music-audit.sh` no longer required operationally.

### V1B — canonical export migration

Deliver:

- migrate `electronic-dj-set-curator` to `tracks.tsv`;
- migrate first-party tests/fixtures/integration/documentation;
- enforce `source_id`/`set_eligible` during selection;
- validate generated M3U8 against canonical `tracks.tsv` rows;
- mark legacy source-specific inventory facets deprecated;
- demonstrate first-party operation with legacy facets disabled.

---

## 15. Explicit V2 candidates

Out of scope for V1/V1B:

- audio fingerprint generation;
- content-based move/rename reconciliation;
- exact/near duplicate detection using audio fingerprints;
- automatic merging of two historical track identities after fingerprint reconciliation;
- web dashboard;
- waveform rendering;
- cue-point writing;
- Engine DJ database mutation;
- source media retagging/modification;
- automatic execution of set-copy operations.

The V1 model must leave room for V2 fingerprinting by keeping internal `track_id` independent of pathname and by retaining lifecycle events/history.

---

## 16. V1 definition of done

The unified V1 is acceptable only if all of the following are true:

1. `export-music-audit.sh` is no longer required to operate DJ Digger.
2. DJ Digger discovers its configured libraries itself.
3. One SQLite database is the canonical persistent state for all configured sources.
4. Export files are reproducible projections, never internal authorities.
5. Tracks are historical records and are not deleted when absent from a later scan.
6. Only a complete successful source scan may mark unseen tracks missing.
7. Missing tracks may be restored without losing history.
8. Source media remain read-only.
9. Existing audit coverage from `export-music-audit.sh`, including empty directories and DJ metadata discovery, is available from catalog-derived facets.
10. Timestamped audit snapshot packaging to a `.tar.gz` archive remains available.
11. Existing V1 DSP/structural analysis coverage remains available.
12. Incrementality is driven by cataloged input facts and analysis versions, not a separately pruned cache.
13. `tracks.tsv` exists in V1A and includes exact relative `path` plus `source_id`.
14. V1A can generate legacy `djing-files.tsv` / `music-files.tsv` compatibility facets.
15. V1B migrates every first-party inventory consumer to `tracks.tsv`.
16. Set-generated paths remain compatible with the external set-copy workflow.
17. Structured exports are versioned, validated and atomically published.
18. Technical uncertainty and per-track failures are surfaced rather than guessed.
19. V2 fingerprint/move/duplicate support can be added without replacing pathname-based primary keys because paths are not primary identity.
