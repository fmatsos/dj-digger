# DJ Digger Catalog and Export V1A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the unified `dj-digger` product foundation: N-source configuration, persistent historical SQLite catalog, single-pass filesystem discovery, embedded metadata, catalog-derived exports, compatibility facets, snapshots and primary CLI workflow.

**Architecture:** The scanner writes observations into a source-scoped run and only reconciles unseen rows after successful traversal. Repositories hide SQL, lifecycle rules own presence transitions, ExifTool owns embedded tags, and exporters query SQLite without walking source filesystems. `refresh` composes these services without making any export an input.

**Tech Stack:** Python 3.12; SQLite; Typer; ExifTool; jsonschema; pytest; Ruff; mypy; Docker/Compose.

**Spec:** `docs/superpowers/specs/2026-08-24-dj-digger-unified-v1-design.md`

## Global Constraints

- Catalog schema version `1`; tracks export schema version `1`.
- `(source_id, relative_path)` is unique in V1 but is not the internal primary identity.
- Source root relocation must not create new tracks when relative paths are unchanged.
- Reconciliation to `missing` occurs only after complete successful traversal.
- Failed scans preserve all prior presence state.
- Empty directories must be cataloged.
- Source media are never opened for write.
- `tracks.tsv` serializes extension with leading dot and mtime as local ISO-8601 second precision.
- Atomic exports must validate before replacing the previous published facet.

---

## Target file map

```text
src/dj_digger/
├── cli.py
├── config.py
├── catalog/{database.py,migrations.py,models.py,repositories.py}
├── scanning/{scanner.py,classifiers.py,lifecycle.py}
├── metadata/exiftool.py
├── artifacts/discovery.py
└── exports/{atomic.py,tracks.py,audit.py,legacy.py,snapshot.py}
tests/
├── fixtures/library/
├── test_config.py
├── test_catalog_migrations.py
├── test_scanner.py
├── test_lifecycle.py
├── test_exiftool.py
├── test_artifacts.py
├── test_tracks_export.py
├── test_legacy_exports.py
├── test_snapshot.py
└── test_cli_refresh.py
```

### Task 1: Bootstrap unified package and workspace configuration

**Files:**
- Create: `pyproject.toml`, `Dockerfile`, `compose.yaml`
- Create: `config/dj-digger.example.toml`
- Create: `src/dj_digger/config.py`, `src/dj_digger/cli.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `WorkspaceConfig.load(path: Path) -> WorkspaceConfig`
- Produces: `LibrarySourceConfig(id: str, path: Path, set_eligible: bool, analyze: bool, enabled: bool)`

- [ ] **Step 1: Write the failing configuration test**

```python
from pathlib import Path
from dj_digger.config import WorkspaceConfig

def test_loads_multiple_sources_with_stable_ids() -> None:
    cfg = WorkspaceConfig.load(Path("tests/fixtures/dj-digger.toml"))
    assert [s.id for s in cfg.sources] == ["djing", "music"]
    assert cfg.sources[0].set_eligible is True
    assert cfg.sources[1].analyze is False
```

- [ ] **Step 2: Run the test and verify failure**

```bash
pytest tests/test_config.py -q
```
Expected: import/configuration failure because the package does not exist.

- [ ] **Step 3: Implement the minimal immutable config model and validation**

```python
@dataclass(frozen=True)
class LibrarySourceConfig:
    id: str
    path: Path
    set_eligible: bool
    analyze: bool
    enabled: bool = True

@dataclass(frozen=True)
class ExportConfig:
    legacy_compatibility: bool = True

@dataclass(frozen=True)
class WorkspaceConfig:
    database: Path
    exports: Path
    export: ExportConfig
    sources: tuple[LibrarySourceConfig, ...]
```
Reject duplicate/blank source IDs and any workspace database/export path nested inside a configured source root. `legacy_compatibility` defaults to `true` in V1A and can be disabled for V1B acceptance.

- [ ] **Step 4: Run tests and static checks**

```bash
pytest tests/test_config.py -q
ruff check src tests
mypy src
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml Dockerfile compose.yaml config src/dj_digger/config.py src/dj_digger/cli.py tests/test_config.py
git commit -m "feat: bootstrap unified DJ Digger workspace"
```

### Task 2: Add explicit transactional catalog migrations and repositories

**Files:**
- Create: `src/dj_digger/catalog/database.py`, `migrations.py`, `models.py`, `repositories.py`
- Copy/reference: `schemas/catalog-v1.sql`
- Test: `tests/test_catalog_migrations.py`

**Interfaces:**
- Produces: `Database.open(path: Path) -> Database`
- Produces: `Database.migrate() -> None`
- Produces: `TrackRepository.find(source_id: str, relative_path: str) -> Track | None`
- Produces: `TrackRepository.present_for_source(source_id: str) -> list[Track]`

- [ ] **Step 1: Write a failing migration/reopen test**

```python
def test_catalog_migration_is_idempotent(tmp_path: Path) -> None:
    db = Database.open(tmp_path / "catalog.sqlite")
    db.migrate()
    db.migrate()
    assert db.scalar("PRAGMA user_version") == 1
    assert db.table_exists("tracks")
    assert db.table_exists("track_events")

def test_source_root_relocation_preserves_track_identity(catalog) -> None:
    track_id = catalog.track_id("djing", "Techno/A.flac")
    catalog.update_source_root("djing", Path("/srv/music/djing"))
    assert catalog.track_id("djing", "Techno/A.flac") == track_id
```

- [ ] **Step 2: Run and verify failure**

```bash
pytest tests/test_catalog_migrations.py -q
```
Expected: FAIL because catalog persistence is absent.

- [ ] **Step 3: Implement migration 001 and focused repositories**

```python
MIGRATIONS = ((1, "001_catalog_v1.sql"),)

def migrate(conn: sqlite3.Connection) -> None:
    with conn:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for version, resource in MIGRATIONS:
            if version > current:
                conn.executescript(load_sql(resource))
                conn.execute(f"PRAGMA user_version = {version}")
```
Keep SQL transactions inside database/repository boundaries; callers must not concatenate ad-hoc SQL.

- [ ] **Step 4: Run persistence tests**

```bash
pytest tests/test_catalog_migrations.py -q
```
Expected: PASS including foreign-key enforcement and unique `(source_id, relative_path)`.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/catalog tests/test_catalog_migrations.py schemas/catalog-v1.sql
git commit -m "feat: add persistent historical catalog"
```

### Task 3: Implement one-pass source scanner and classification

**Files:**
- Create: `src/dj_digger/scanning/scanner.py`, `classifiers.py`
- Create: `src/dj_digger/artifacts/discovery.py`
- Test: `tests/test_scanner.py`, `tests/test_artifacts.py`

**Interfaces:**
- Produces: `SourceScanner.scan(source: LibrarySourceConfig, run_id: int) -> ScanObservation`
- `ScanObservation` contains exact audio paths, all directory paths, supported DJ artifacts and counters.

- [ ] **Step 1: Write failing fixture tests for audio, empty directories and artifacts**

```python
def test_single_scan_observes_audio_empty_dirs_and_serato(tmp_library: Path) -> None:
    result = scanner.scan(source, run_id=1)
    assert "Techno/A.flac" in result.audio_paths
    assert "Empty" in result.directory_paths
    assert result.artifacts["_Serato_/Subcrates/Acid.crate"].type == "serato_crate"
```

- [ ] **Step 2: Run scanner tests**

```bash
pytest tests/test_scanner.py tests/test_artifacts.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement `os.scandir`/walk traversal with exact path preservation**

```python
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac", ".ogg", ".opus"}

def classify(relative: Path, is_dir: bool) -> EntryKind:
    if is_dir:
        return EntryKind.DIRECTORY
    if relative.suffix.lower() in AUDIO_EXTENSIONS:
        return EntryKind.AUDIO
    return classify_dj_artifact(relative)
```
Use the exact filesystem-relative spelling for persisted/exported `path`; lowercasing is allowed only for extension/classification comparisons.

- [ ] **Step 4: Run tests including read-only spy**

```bash
pytest tests/test_scanner.py tests/test_artifacts.py -q
```
Expected: PASS and no source file opened with write/append/update mode.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/scanning src/dj_digger/artifacts tests/test_scanner.py tests/test_artifacts.py
git commit -m "feat: scan library sources in one traversal"
```

### Task 4: Implement commit-on-success lifecycle reconciliation and events

**Files:**
- Create: `src/dj_digger/scanning/lifecycle.py`
- Modify: `src/dj_digger/catalog/repositories.py`
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Produces: `ScanLifecycle.begin(source_id: str) -> int`
- Produces: `ScanLifecycle.observe(run_id: int, observation: ScanObservation) -> None`
- Produces: `ScanLifecycle.succeed(run_id: int) -> ReconciliationResult`
- Produces: `ScanLifecycle.fail(run_id: int, stage: str, error: str) -> None`

- [ ] **Step 1: Write failing success/failure/restoration tests**

```python
def test_failed_scan_never_marks_unseen_tracks_missing(catalog) -> None:
    first = successful_scan(catalog, {"A.flac", "B.flac"})
    failed_scan(catalog, observed={"A.flac"})
    assert catalog.track("B.flac").presence_status == "present"

def test_successful_scan_marks_and_restores(catalog) -> None:
    successful_scan(catalog, {"A.flac"})
    successful_scan(catalog, set())
    assert catalog.track("A.flac").presence_status == "missing"
    successful_scan(catalog, {"A.flac"})
    assert catalog.track("A.flac").presence_status == "present"
```

- [ ] **Step 2: Run lifecycle tests**

```bash
pytest tests/test_lifecycle.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement transactional reconciliation**

```python
with db.transaction():
    run = runs.require_running(run_id)
    tracks.mark_missing_not_seen(source_id=run.source_id, scan_run_id=run_id, at=now)
    artifacts.mark_missing_not_seen(source_id=run.source_id, scan_run_id=run_id, at=now)
    directories.mark_missing_not_seen(source_id=run.source_id, scan_run_id=run_id, at=now)
    runs.mark_succeeded(run_id, finished_at=now)
    sources.set_last_successful_scan(run.source_id, run_id)
```
`fail()` updates only run diagnostics and never executes reconciliation.

- [ ] **Step 4: Run lifecycle tests**

```bash
pytest tests/test_lifecycle.py -q
```
Expected: PASS with `discovered`, `missing`, `restored`, and `filesystem_metadata_changed` events.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/scanning/lifecycle.py src/dj_digger/catalog/repositories.py tests/test_lifecycle.py
git commit -m "feat: preserve source history across scans"
```

### Task 5: Normalize ExifTool embedded metadata into catalog state

**Files:**
- Create: `src/dj_digger/metadata/exiftool.py`
- Modify: `src/dj_digger/catalog/repositories.py`
- Test: `tests/test_exiftool.py`

**Interfaces:**
- Produces: `ExifToolExtractor.extract(track: Track) -> EmbeddedMetadata`
- Produces: `MetadataService.refresh(source_id: str | None, force: bool = False) -> MetadataRunResult`

- [ ] **Step 1: Write a failing normalization test**

```python
def test_exiftool_maps_only_embedded_tag_ownership() -> None:
    meta = extractor.normalize({"Title":"Acid", "Artist":"X", "BPM":145, "Duration":123.4})
    assert meta.title == "Acid"
    assert meta.tag_bpm == 145
    assert not hasattr(meta, "duration_seconds")
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_exiftool.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement batched ExifTool read and refresh eligibility**

```python
EMBEDDED_FIELDS = ("Title","Artist","AlbumArtist","Album","Track","DiscNumber","Genre","Date","Year","Composer","Comment","BPM","InitialKey","Grouping")
```
Refresh only new/changed tracks, extractor-version changes, normalization-version changes, or explicit `--force`. Record per-track failures without changing filesystem presence. When the normalized tag payload changes, append one `embedded_metadata_changed` event containing changed field names, not an opaque duplicate snapshot.

- [ ] **Step 4: Run metadata tests**

```bash
pytest tests/test_exiftool.py -q
```
Expected: PASS, including malformed tags and files with embedded newlines.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/metadata src/dj_digger/catalog/repositories.py tests/test_exiftool.py
git commit -m "feat: normalize embedded metadata into catalog"
```

### Task 6: Publish canonical `tracks.tsv` atomically from SQLite

**Files:**
- Create: `src/dj_digger/exports/atomic.py`, `tracks.py`
- Copy: `schemas/tracks.schema.json`, `schema-bundle.json`
- Test: `tests/test_tracks_export.py`

**Interfaces:**
- Produces: `TracksExporter.export(destination: Path) -> PublishedFacet`
- Consumes: present tracks joined with current source config, embedded metadata and technical metadata.

- [ ] **Step 1: Write a failing schema/header/path test**

```python
def test_tracks_export_is_present_only_and_source_aware(tmp_path: Path) -> None:
    facet = exporter.export(tmp_path / "tracks.tsv")
    rows = read_tsv(facet.path)
    assert list(rows[0]) == schema_columns("schemas/tracks.schema.json")
    assert {r["path"] for r in rows} == {"Techno/A.flac"}
    assert rows[0]["source_id"] == "djing"
```

- [ ] **Step 2: Run export test**

```bash
pytest tests/test_tracks_export.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement deterministic serialization and validate-before-rename**

```python
tmp = destination.with_suffix(destination.suffix + ".tmp")
write_rows(tmp, rows, columns=schema_columns)
validate_tsv(tmp, schema)
os.replace(tmp, destination)
```
Derive `absolute_path` at export time. Serialize `extension` with leading dot and `mtime` as `YYYY-MM-DDTHH:MM:SS`.

- [ ] **Step 4: Run tests including invalid-publication protection**

```bash
pytest tests/test_tracks_export.py -q
```
Expected: PASS and the previous valid file remains unchanged if validation fails.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/exports schemas/tracks.schema.json schema-bundle.json tests/test_tracks_export.py
git commit -m "feat: publish canonical tracks facet"
```

### Task 7: Reproduce historical audit and compatibility facets without rescanning

**Files:**
- Create: `src/dj_digger/exports/audit.py`, `legacy.py`
- Copy/reference: `references/export-music-audit.sh`
- Test: `tests/test_legacy_exports.py`

**Interfaces:**
- Produces legacy source projections and `library-artifacts.tsv` from repository queries only.

- [ ] **Step 1: Write parity tests for the historical five-column inventory and directory summaries**

```python
def test_legacy_inventory_contract() -> None:
    header = legacy_header("djing-files.tsv")
    assert header == ["path","filename","extension","size_bytes","mtime"]

def test_directory_counts_come_from_catalog_not_filesystem(monkeypatch) -> None:
    monkeypatch.setattr(Path, "rglob", lambda *_: (_ for _ in ()).throw(AssertionError("rescan")))
    exporter.export_directory_stats("djing")
```

- [ ] **Step 2: Run parity tests**

```bash
pytest tests/test_legacy_exports.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement catalog-derived facets**

Generate `djing-files.tsv`, `music-files.tsv`, source metadata CSVs, directory lists, depth-3 trees, level-1/2 stats, summaries, `library-artifacts.tsv`, `dj-metadata-files.tsv`, `serato-directories.txt`, `traktor-files.tsv`, and `README.txt`/manifest from SQL state. The compatibility metadata CSV keeps the historical useful columns (`SourceFile`, `FileName`, `Directory`, `FileType`, `FileSize`, `Duration`, `AudioBitrate`, `SampleRate`, `Title`, `Artist`, `AlbumArtist`, `Album`, `Track`, `DiscNumber`, `Genre`, `Date`, `Year`, `Composer`, `Comment`, `BPM`, `InitialKey`, `Grouping`) while sourcing overlapping technical facts from FFmpeg-owned catalog fields. Respect `export.legacy_compatibility`; disabling it omits source-specific compatibility facets without affecting canonical facets.

```python
def export_source_summary(source_id: str) -> SourceSummary:
    return repos.stats.for_source(source_id, present_only=True)
```

- [ ] **Step 4: Run parity/schema tests**

```bash
pytest tests/test_legacy_exports.py -q
```
Expected: PASS; no exporter performs a filesystem traversal.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/exports tests/test_legacy_exports.py references/export-music-audit.sh schemas/library-artifacts.schema.json
git commit -m "feat: preserve historical audit facets"
```

### Task 8: Add deterministic snapshot directory and tar.gz packaging

**Files:**
- Create: `src/dj_digger/exports/snapshot.py`
- Copy: `schemas/snapshot-manifest.schema.json`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Produces: `SnapshotExporter.create(output: Path, archive: bool) -> SnapshotResult`

- [ ] **Step 1: Write failing manifest/archive test**

```python
def test_snapshot_contains_hash_manifest_and_archive(tmp_path: Path) -> None:
    result = snapshots.create(tmp_path, archive=True)
    manifest = json.loads((result.directory / "snapshot-manifest.json").read_text())
    assert "tracks.tsv" in {f["name"] for f in manifest["facets"]}
    assert result.archive.name.endswith(".tar.gz")
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_snapshot.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement one consistent read transaction and manifest hashes**

```python
with db.read_transaction():
    facets = export_all_into(staging_dir)
    manifest = build_manifest(facets, source_freshness=source_repo.all())
validate_json(manifest, snapshot_schema)
atomic_rename(staging_dir, final_dir)
```
Archive only after successful publication of the directory.

- [ ] **Step 4: Run snapshot tests**

```bash
pytest tests/test_snapshot.py -q
```
Expected: PASS and every recorded SHA-256 matches its facet.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/exports/snapshot.py schemas/snapshot-manifest.schema.json tests/test_snapshot.py
git commit -m "feat: add self-describing audit snapshots"
```

### Task 9: Wire `scan`, `metadata`, `export`, `snapshot`, `status`, `doctor` and `refresh`

**Files:**
- Modify: `src/dj_digger/cli.py`
- Create: `src/dj_digger/application.py`, `src/dj_digger/logging.py`
- Test: `tests/test_cli_refresh.py`, `tests/test_cli_status_doctor.py`

**Interfaces:**
- Produces CLI commands defined by the approved spec.
- `refresh` publishes canonical exports only when required/set-eligible source scans are fresh/successful.

- [ ] **Step 1: Write failing CLI orchestration tests**

```python
def test_refresh_does_not_publish_when_required_scan_fails(runner) -> None:
    result = runner.invoke(app, ["refresh", "--config", "tests/fixtures/failing.toml"])
    assert result.exit_code != 0
    assert published_tracks_checksum() == PREVIOUS_CHECKSUM
```

- [ ] **Step 2: Run CLI tests**

```bash
pytest tests/test_cli_refresh.py tests/test_cli_status_doctor.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement application service sequencing**

```python
def refresh(cfg: WorkspaceConfig) -> RefreshResult:
    scan_results = scan_enabled_sources(cfg)
    if any(r.failed and r.source.set_eligible for r in scan_results):
        return RefreshResult.failed_without_publication(scan_results)
    metadata_result = metadata.refresh()
    return export_current_facets(scan_results, metadata_result)
```
Analysis orchestration is plugged into this service by the analysis workstream, not reimplemented here. `doctor` checks configured roots, workspace placement, SQLite migration state and required binaries (`exiftool`, `ffprobe`, `ffmpeg`); `status` reports source freshness, last successful/failed scan, present/missing counts and last analysis/export state. Each command writes structured run diagnostics plus a human-readable log outside source roots.

- [ ] **Step 4: Run package quality gate**

```bash
pytest -q
ruff check .
mypy src
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/application.py src/dj_digger/cli.py tests/test_cli_refresh.py
git commit -m "feat: expose unified DJ Digger catalog workflow"
```
