# Duplicate Mastering and DJ Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add versioned EBU R128 mastering measurements, descriptive DJ gain metrics, exact-duplicate group comparisons, review filtering, and exports without changing the technical-only meaning of `best_quality`.

**Architecture:** Keep raw mastering attempts append-only in SQLite V9, project the latest successful measurement separately, and derive target-dependent DJ metrics in a rebuildable projection that does not require audio decoding when targets change. Extend the existing exact-Chromaprint `duplicates` flow with opt-in heavy analysis and compute group flags relative to an explicitly marked `best_quality` member.

**Tech Stack:** Python 3.12, Typer, SQLite, FFmpeg/FFprobe `ebur128`, Rich, pytest, Ruff, mypy, JSON Schema.

**Spec:** `docs/superpowers/specs/2026-08-28-duplicate-mastering-dj-analysis-design.md`

## Global Constraints

- Duplicate identity remains complete exact-Chromaprint equality; do not add similarity matching.
- `best_quality` and `QualitySelector` remain technical-only and must not consume mastering or DJ metrics.
- Heavy mastering analysis is opt-in and limited to present members of exact duplicate groups.
- `MASTERING_ANALYSIS_VERSION` is code-owned; workspace configuration cannot override it.
- Default targets are `dj_target_lufs = -9.0` and `dj_target_true_peak_dbtp = -1.0`.
- Threshold decisions use `abs(delta) >= threshold`; serialized deltas remain signed.
- FFmpeg workers never write SQLite; only the parent process persists results.
- Source audio is read-only and its bytes must remain unchanged in public-path proof.
- `config/local.toml`, `workspace/`, `sets/`, `*.sqlite*`, and unrelated worktree changes are never modified or staged.
- Commit steps require explicit Git authorization at execution time; otherwise stop after verified working-tree changes.

---

### Task 1: Add mastering configuration and pure metric calculations

**Files:**
- Modify: `src/dj_digger/config.py`
- Create: `src/dj_digger/duplicates/mastering.py`
- Create: `tests/test_mastering_metrics.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: workspace TOML loaded by `WorkspaceConfig.load(path)`.
- Produces: `MasteringConfig`, `MasteringMeasurements`, `DjMetrics`, `percentiles()`, `derive_mastering_measurements()`, and `derive_dj_metrics()` for persistence and comparison tasks.

- [ ] **Step 1: Write failing tests for defaults and strict configuration validation**

```python
def test_workspace_config_uses_mastering_defaults(valid_config: Path) -> None:
    config = WorkspaceConfig.load(valid_config)
    assert config.mastering.dj_target_lufs == -9.0
    assert config.mastering.dj_target_true_peak_dbtp == -1.0
    assert config.mastering.variant_thresholds.plr_db == 2.0


@pytest.mark.parametrize("value", [float("inf"), float("nan"), "-9"])
def test_mastering_targets_must_be_finite_numbers(valid_config: Path, value: object) -> None:
    write_mastering_value(valid_config, "dj_target_lufs", value)
    with pytest.raises(ValueError, match="mastering.dj_target_lufs"):
        WorkspaceConfig.load(valid_config)
```

- [ ] **Step 2: Run the focused tests and observe RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_config.py -q`

Expected: FAIL because `WorkspaceConfig.mastering` and validation do not exist.

- [ ] **Step 3: Implement immutable configuration types and defaults**

Add `ComparisonThresholds` and `MasteringConfig` dataclasses. Parse optional `[mastering]`, `[mastering.variant_thresholds]`, and `[mastering.review_thresholds]` tables; reject non-finite targets and negative thresholds. Do not expose the analysis version in TOML.

```python
@dataclass(frozen=True)
class ComparisonThresholds:
    active_loudness_db: float
    true_peak_db: float
    plr_db: float
    integrated_lufs_db: float | None = None
    lra_lu: float | None = None
    gain_deficit_db: float | None = None


@dataclass(frozen=True)
class MasteringConfig:
    dj_target_lufs: float = -9.0
    dj_target_true_peak_dbtp: float = -1.0
    variant_thresholds: ComparisonThresholds = VARIANT_DEFAULTS
    review_thresholds: ComparisonThresholds = REVIEW_DEFAULTS
```

- [ ] **Step 4: Write failing unit tests for percentiles and derived metrics**

```python
def test_gain_without_deficit() -> None:
    result = derive_dj_metrics(-13.0, -5.0, target_lufs=-9.0, target_peak_dbtp=-1.0)
    assert result == DjMetrics(4.0, 4.0, 0.0)


def test_gain_with_peak_limited_deficit() -> None:
    result = derive_dj_metrics(-13.0, -0.2, target_lufs=-9.0, target_peak_dbtp=-1.0)
    assert result.required_gain_db == pytest.approx(4.0)
    assert result.available_gain_db == pytest.approx(-0.8)
    assert result.gain_deficit_db == pytest.approx(4.8)


def test_missing_or_non_finite_values_propagate_to_null() -> None:
    assert derive_dj_metrics(None, -1.0, target_lufs=-9.0, target_peak_dbtp=-1.0) == (
        DjMetrics(None, 0.0, None)
    )
    assert percentiles([float("nan"), float("inf")]) == (None, None)
```

- [ ] **Step 5: Run metric tests and observe RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_mastering_metrics.py -q`

Expected: FAIL because `dj_digger.duplicates.mastering` does not exist.

- [ ] **Step 6: Implement the pure calculation layer**

Use finite-value filtering and one documented linear percentile interpolation. Preserve full floating-point precision internally.

```python
MASTERING_ANALYSIS_VERSION = "ffmpeg-ebur128/1"

@dataclass(frozen=True)
class MasteringMeasurements:
    integrated_lufs: float | None
    loudness_range_lu: float | None
    true_peak_dbtp: float | None
    short_term_lufs_p50: float | None
    short_term_lufs_p95: float | None
    peak_to_loudness_ratio_db: float | None


@dataclass(frozen=True)
class DjMetrics:
    required_gain_db: float | None
    available_gain_db: float | None
    gain_deficit_db: float | None
```

- [ ] **Step 7: Run focused GREEN and static checks**

Run:

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_config.py tests/test_mastering_metrics.py -q
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools uvx ruff check src/dj_digger/config.py src/dj_digger/duplicates/mastering.py tests/test_config.py tests/test_mastering_metrics.py
```

Expected: PASS.

- [ ] **Step 8: Create a scoped commit if explicitly authorized**

Use the project `commit` skill with subject `feat: add mastering metric model`. Its body must record the metric/configuration goal, the four changed files, the focused pytest/Ruff proof, and any remaining FFmpeg-integration risk.

---

### Task 2: Extract structured EBU R128 measurements with bounded FFmpeg

**Files:**
- Create: `src/dj_digger/analysis/ebur128.py`
- Create: `tests/test_ebur128.py`
- Modify: `tests/test_ffmpeg.py`

**Interfaces:**
- Consumes: `MasteringMeasurements` and `derive_mastering_measurements()` from Task 1.
- Produces: `EbuR128Analyzer.analyze(path: Path, *, timeout: float) -> MasteringMeasurements` and `EbuR128AnalysisError` for duplicate orchestration.

- [ ] **Step 1: Write failing parser tests using bounded public FFmpeg output samples**

```python
def test_parser_extracts_summary_and_short_term_percentiles() -> None:
    result = parse_ebur128_output(EBUR128_METADATA_AND_SUMMARY)
    assert result.integrated_lufs == pytest.approx(-10.8)
    assert result.loudness_range_lu == pytest.approx(4.2)
    assert result.true_peak_dbtp == pytest.approx(-0.4)
    assert result.short_term_lufs_p50 == pytest.approx(-9.8)
    assert result.short_term_lufs_p95 == pytest.approx(-8.4)
    assert result.peak_to_loudness_ratio_db == pytest.approx(10.4)


def test_parser_keeps_available_summary_when_short_term_is_missing() -> None:
    result = parse_ebur128_output(SUMMARY_ONLY)
    assert result.integrated_lufs == -23.0
    assert result.short_term_lufs_p50 is None
    assert result.short_term_lufs_p95 is None
```

- [ ] **Step 2: Run parser tests and observe RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_ebur128.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement a locale-independent structured analyzer**

Invoke FFmpeg without a shell. Use `ebur128=metadata=1:peak=true`, emit frame metadata with `ametadata`, disable video, and capture bounded text output. Parse `lavfi.r128.S` samples plus the final I/LRA/Peak summary; reject non-zero exits and output that cannot be recognized as an EBU result. Recognized infinite silence values normalize to null rather than failing the attempt. Force `LC_ALL=C` and `LANG=C` in a copied child-process environment so summary labels are stable without mutating the parent environment.

```python
argv = [
    self._ffmpeg, "-nostdin", "-v", "info", "-i", str(path),
    "-map", "0:a:0", "-filter:a",
    "ebur128=metadata=1:peak=true,ametadata=print:file=-",
    "-vn", "-f", "null", "-",
]
```

Convert `subprocess.TimeoutExpired` to `EbuR128AnalysisError(stage="timeout", ...)`; bound captured diagnostics and never include private absolute paths in returned or persisted messages.

- [ ] **Step 4: Add process-boundary tests**

Test argv safety for paths containing spaces and shell characters, forced child locale, unrelated/localized surrounding log text, non-zero exit, timeout, empty output, mono input, silence, and a very short generated WAV. Process fakes may verify isolated parsing/error classification, but the final integration proof must invoke real FFmpeg.

- [ ] **Step 5: Run focused GREEN**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_ebur128.py tests/test_ffmpeg.py -q`

Expected: PASS, including controlled null metrics for silence/short input where FFmpeg supplies no finite loudness.

- [ ] **Step 6: Run Ruff and mypy for the new boundary**

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools uvx ruff check src/dj_digger/analysis/ebur128.py tests/test_ebur128.py
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools uvx --with typer mypy src/dj_digger/analysis/ebur128.py src/dj_digger/duplicates/mastering.py
```

- [ ] **Step 7: Create a scoped commit if explicitly authorized**

Use the project `commit` skill with subject `feat: extract ebu r128 mastering metrics`. Its bounded brief must name the analyzer/parser files, focused tests and static proof, and any platform-specific FFmpeg reservation.

---

### Task 3: Migrate the catalog to V9

**Files:**
- Create: `src/dj_digger/catalog/sql/catalog-v9.sql`
- Create: `src/dj_digger/catalog/sql/migrate-v8-to-v9.sql`
- Create: `schemas/catalog-v9.sql`
- Modify: `src/dj_digger/catalog/migrations.py`
- Modify: `tests/test_catalog_migrations.py`

**Interfaces:**
- Consumes: column names from `MasteringMeasurements` and `DjMetrics`.
- Produces: append-only `mastering_analysis`, rebuildable `current_mastering_analysis`, and rebuildable `current_dj_analysis` tables.

- [ ] **Step 1: Write failing V8-to-V9 preservation and schema-contract tests**

Assert that a populated V8 database preserves sources, tracks, fingerprints, duplicate selections, historical DSP analyses, and current projections. Assert table columns, foreign keys, status check, lookup indexes, and `PRAGMA user_version = 9`.

```python
assert columns(connection, "mastering_analysis") == EXPECTED_MASTERING_COLUMNS
assert columns(connection, "current_mastering_analysis") == EXPECTED_CURRENT_COLUMNS
assert columns(connection, "current_dj_analysis") == EXPECTED_DJ_COLUMNS
assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
```

- [ ] **Step 2: Run migration tests and observe RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_catalog_migrations.py -q`

Expected: FAIL because current version is 8 and V9 resources do not exist.

- [ ] **Step 3: Add packaged V9 schema and transactional forward migration**

Add foreign keys to `tracks` and `mastering_analysis`, success lookup/history indexes, finite-value checks where SQLite can enforce them, and status constraint `CHECK (status IN ('succeeded','failed'))`. Mastering history uses the same restrictive track-deletion policy as `audio_analysis`: no `ON DELETE CASCADE` on `mastering_analysis.track_id`; physical track removal requires explicit history cleanup, while current projections are rebuildable and cascade after their history is removed. Define the final V9 `library_tracks` view now, including the nine nullable mastering/DJ columns required by Task 8, so the migration is never rewritten after adoption. Do not add a downgrade runner. Update:

```python
CURRENT_VERSION = 9
CURRENT_SCHEMA = "catalog-v9.sql"
MIGRATIONS = {
    6: "migrate-v6-to-v7.sql",
    7: "migrate-v7-to-v8.sql",
    8: "migrate-v8-to-v9.sql",
}
```

- [ ] **Step 4: Prove fresh schema parity and atomic failure rollback**

Add a test comparing `schemas/catalog-v9.sql` byte-for-byte with the packaged schema. Inject a migration failure inside a temporary copied script or controlled connection hook and assert V8 objects/data and `user_version` remain unchanged. Add a deletion test proving a track with mastering history is restricted until its explicit mastering attempts are removed, after which both current projections disappear and the track can be deleted.

- [ ] **Step 5: Run catalog GREEN**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_catalog_migrations.py -q`

Expected: PASS with zero foreign-key violations.

- [ ] **Step 6: Create a scoped commit if explicitly authorized**

Use the project `commit` skill with subject `feat: add mastering analysis catalog schema`. Its bounded brief must name the packaged/fresh schemas, migration registry and tests, the observed preservation/rollback/foreign-key proof, and residual compatibility risk.

---

### Task 4: Persist attempts and rebuild current projections

**Files:**
- Create: `src/dj_digger/duplicates/mastering_repository.py`
- Create: `tests/test_mastering_persistence.py`

**Interfaces:**
- Consumes: `Track`, `MasteringMeasurements`, `DjMetrics`, `MasteringConfig`, and V9 tables.
- Produces: `CurrentMasteringAnalysis`, `CurrentDjAnalysis`, `MasteringRepository.reusable()`, `persist_success()`, `persist_failure()`, `rebuild_current()`, `rebuild_dj()`, and `current_for_tracks()`.

- [ ] **Step 1: Write failing append-only and latest-success tests**

```python
def test_newer_failure_does_not_replace_latest_success(database: Database, track: Track) -> None:
    repository = MasteringRepository(database)
    success_id = persist_success(repository, track, integrated=-11.0)
    repository.persist_failure(track, MASTERING_ANALYSIS_VERSION, "decode", "failed")
    assert repository.current_for_tracks([track.id])[track.id].analysis_id == success_id
```

Also test immutable history, input/version reuse, file identity invalidation, projection rebuild idempotence, target-only DJ rebuild, null propagation, error-message bounds, and deletion behavior.

- [ ] **Step 2: Run persistence tests and observe RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_mastering_persistence.py -q`

Expected: FAIL because the repository does not exist.

- [ ] **Step 3: Implement parent-owned transactional persistence**

Use parameterized SQL and existing `Database.transaction()` (`BEGIN IMMEDIATE`). Insert one immutable attempt, then update the current mastering projection only for success. Rebuild current state from `MAX(id)` among compatible successful attempts. Rebuild DJ rows from current raw measurements and target parameters without invoking FFmpeg.

```python
@dataclass(frozen=True)
class CurrentMasteringAnalysis:
    analysis_id: int
    track_id: int
    analysis_version: str
    measurements: MasteringMeasurements


@dataclass(frozen=True)
class CurrentDjAnalysis:
    track_id: int
    mastering_analysis_id: int
    target_lufs: float
    target_peak_dbtp: float
    metrics: DjMetrics


def reusable(self, track: Track, analysis_version: str) -> CurrentMasteringAnalysis | None: ...

def persist_success(
    self, track: Track, analysis_version: str, measurements: MasteringMeasurements
) -> int: ...

def persist_failure(
    self, track: Track, analysis_version: str, stage: str, message: str
) -> int: ...

def rebuild_dj(self, target_lufs: float, target_peak_dbtp: float) -> int: ...
```

- [ ] **Step 4: Prove concurrency and rollback behavior with independent file-backed connections**

Open separate database connections, hold a competing `BEGIN IMMEDIATE`, verify configured busy-timeout behavior, then prove a failed projection mutation rolls back its attempt and projection changes atomically.

- [ ] **Step 5: Run focused GREEN and foreign-key check**

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_mastering_persistence.py tests/test_current_analysis.py -q
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools uvx ruff check src/dj_digger/duplicates/mastering_repository.py tests/test_mastering_persistence.py
```

- [ ] **Step 6: Create a scoped commit if explicitly authorized**

Use the project `commit` skill with subject `feat: persist mastering analysis history`. Its bounded brief must state repository ownership, append-only/projection/concurrency proof, and any remaining service-integration risk.

---

### Task 5: Analyze only exact duplicate-group members

**Files:**
- Create: `src/dj_digger/duplicates/mastering_service.py`
- Modify: `src/dj_digger/duplicates/service.py`
- Modify: `src/dj_digger/application.py`
- Create: `tests/test_mastering_service.py`
- Modify: `tests/test_duplicates_service.py`

**Interfaces:**
- Consumes: `DuplicateRepository.groups()`, `EbuR128Analyzer`, `MasteringRepository`, `MasteringConfig`, and existing progress reporting.
- Produces: `MasteringAnalysisResult` and an optional mastering phase in `DuplicateService.analyze(..., mastering: bool = False)`.

- [ ] **Step 1: Write failing service tests for eligibility and reuse**

Assert:

- isolated present tracks are never submitted to EBU analysis;
- every member of an exact group is eligible;
- current successes are reused;
- input/version changes reschedule only affected members;
- target-only changes rebuild DJ projection with zero analyzer calls;
- successes persist immediately before the next future completes;
- failures continue, are counted, and return a partial result;
- active FFmpeg calls never exceed `workers`.

- [ ] **Step 2: Run service tests and observe RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_mastering_service.py tests/test_duplicates_service.py -q`

Expected: FAIL because no mastering phase exists.

- [ ] **Step 3: Implement bounded orchestration**

Derive unique member tracks from `DuplicateRepository.groups(source_id)` after the fingerprint phase. Schedule at most `workers` analyzer calls using the existing bounded-future pattern. Persist only on the parent thread. Return explicit counters:

```python
@dataclass(frozen=True)
class MasteringAnalysisResult:
    files_total: int
    analyzed: int
    reused: int
    failed: int
```

Extend `DuplicateAnalysisResult` with exact integer fields `mastering_files_total`, `mastering_analyzed`, `mastering_reused`, and `mastering_failed`, all defaulting to zero, plus an explicit `status` property. Plain `--analyze` retains its current status calculation. With `mastering=True`, use this truth table:

```text
fingerprint failures with no fingerprint analyzed or reused -> failed
any other fingerprint or mastering per-track failure       -> partial
zero eligible mastering members and no fingerprint failure -> succeeded
no failures                                                -> succeeded
```

Thus an all-reused fingerprint phase followed by all mastering failures is `partial`, not `failed`, because duplicate indexing remains valid. Command-level initialization, configuration, or catalog exceptions remain `failed` through `_run`.

- [ ] **Step 4: Preserve technical ranking behavior explicitly**

Add a regression test that records the selected track, runs mastering analysis with deliberately divergent loudness metrics, reruns `mark_best_quality`, and asserts the same preferred track. Do not modify `_rank_key`, `RANKING_VERSION`, or `TechnicalFacts`.

- [ ] **Step 5: Run focused GREEN**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_mastering_service.py tests/test_duplicates_service.py tests/test_duplicate_quality.py -q`

Expected: PASS; quality tests remain byte-for-byte semantically unchanged.

- [ ] **Step 6: Run analysis safety checks**

Verify Python 3.12, bounded child count, parent-only SQLite writes, visible timeout/crash classification, and bounded diagnostics. Record inaccessible private-library execution as unverified.

Add a file-backed service-level concurrency test with independent reader and writer connections. Complete two analyzer futures in a controlled order, assert workers never receive a database handle, and prove the first result becomes visible to the reader after its own transaction before the second future completes.

- [ ] **Step 7: Create a scoped commit if explicitly authorized**

Use the project `commit` skill with subject `feat: analyze duplicate mastering metrics`. Its bounded brief must list the orchestration/application/test files, worker and public-state proof, unchanged quality-ranking proof, and remaining CLI risk.

---

### Task 6: Compare members with the marked technical winner

**Files:**
- Create: `src/dj_digger/duplicates/mastering_comparison.py`
- Modify: `src/dj_digger/duplicates/service.py`
- Create: `tests/test_mastering_comparison.py`
- Modify: `tests/test_duplicates_service.py`

**Interfaces:**
- Consumes: current mastering/DJ rows, `MasteringConfig`, and `DuplicateRepository.quality_selections()`.
- Produces: `compare_member(member, baseline, thresholds) -> MasteringComparison`, `compare_group(members, preferred_track_id, config) -> GroupMasteringComparison`, enriched `DuplicateMemberDescription`, and enriched `DuplicateGroupDescription` with `comparison_status`, `analysis_complete`, `mastering_variant`, and `dj_review_recommended`.

- [ ] **Step 1: Write failing signed-delta and threshold tests**

```python
def test_negative_delta_meeting_threshold_flags_variant() -> None:
    comparison = compare_member(member_lufs=-13.0, baseline_lufs=-11.5, threshold=1.5)
    assert comparison.loudness_delta_db == -1.5
    assert comparison.mastering_variant is True


def test_missing_best_quality_makes_flags_null() -> None:
    group = compare_group(members, preferred_track_id=None, config=config)
    assert group.comparison_status == "missing_best_quality"
    assert group.mastering_variant is None
    assert group.dj_review_recommended is None
```

Cover inclusive boundaries, positive/negative deltas, missing individual metrics, missing analyses, complete groups, and independently configured variant/review thresholds.

- [ ] **Step 2: Run comparison tests and observe RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_mastering_comparison.py -q`

Expected: FAIL because comparison types do not exist.

- [ ] **Step 3: Implement pure comparison and enrichment**

Keep signed nullable deltas. Use `abs(delta) >= threshold` only for decisions. Define statuses exactly as `complete`, `incomplete`, and `missing_best_quality`. A group is complete only when every present member has a compatible current mastering row and current DJ row.

- [ ] **Step 4: Implement deterministic review sorting**

For recommended groups, sort by maximum non-null member gain deficit descending, then maximum absolute review-metric delta descending, then `group_id` ascending. Missing sort values follow present values.

- [ ] **Step 5: Run focused GREEN**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_mastering_comparison.py tests/test_duplicates_service.py -q`

Expected: PASS.

- [ ] **Step 6: Create a scoped commit if explicitly authorized**

Use the project `commit` skill with subject `feat: compare duplicate masterings`. Its bounded brief must describe signed deltas, threshold/status/sort proof, changed files, and remaining presentation risk.

---

### Task 7: Expose mastering analysis and DJ review in the CLI

**Files:**
- Modify: `src/dj_digger/cli.py`
- Modify: `src/dj_digger/application.py`
- Modify: `tests/test_cli_duplicates.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: enriched duplicate descriptions and `DuplicateService.analyze(..., mastering=...)`.
- Produces: public `--mastering` and `--dj-review` flags plus nested JSON output.

- [ ] **Step 1: Write failing option-matrix tests before application construction**

```python
@pytest.mark.parametrize("args", [
    ["duplicates", "--mastering"],
    ["duplicates", "--list", "--mastering"],
    ["duplicates", "--analyze", "--dj-review"],
])
def test_invalid_mastering_options_fail_before_opening_catalog(args: list[str]) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 2
```

Also test valid `--analyze --mastering`, `--analyze --mastering --mark-best-quality`, `--list --dj-review`, source propagation, background argv, workers, timeout, JSON/stdout, diagnostics/stderr, and partial exit code 2.

- [ ] **Step 2: Run CLI tests and observe RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_cli_duplicates.py tests/test_cli.py -q`

Expected: FAIL because flags and JSON fields are absent.

- [ ] **Step 3: Add flags and public application delegation**

Extend the current command signature with annotated booleans. Validate combinations before `_run`. Preserve the plain `--analyze`, `--list`, and `--mark-best-quality` contracts.

```python
mastering: Annotated[bool, typer.Option("--mastering")] = False
dj_review: Annotated[bool, typer.Option("--dj-review")] = False
```

- [ ] **Step 4: Serialize the approved nested contract**

Extend `_group_json()` with group flags/status and member `audio_analysis`, `dj_analysis`, and `mastering_comparison`. Emit JSON `null` for unavailable numeric values and flags. Filter only groups whose `dj_review_recommended is True`.

- [ ] **Step 5: Run CLI GREEN and real help proof**

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_cli_duplicates.py tests/test_cli.py -q
UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 dj-digger duplicates --help
```

Expected: tests PASS; help lists both flags and preserves existing options.

- [ ] **Step 6: Create a scoped commit if explicitly authorized**

Use the project `commit` skill with subject `feat: expose duplicate mastering review`. Its bounded brief must name the CLI/application/tests, option-matrix/help/exit-code proof, and remaining export risk.

---

### Task 8: Publish per-track mastering and DJ fields

**Files:**
- Modify: `src/dj_digger/catalog/read_repositories.py`
- Modify: `src/dj_digger/exports/tracks.py`
- Modify: `src/dj_digger/exports/snapshot.py`
- Modify: `schemas/tracks.schema.json`
- Modify: `schemas/snapshot-manifest.schema.json`
- Modify: `tests/test_tracks_export.py`
- Modify: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `current_mastering_analysis` and `current_dj_analysis`.
- Produces: nullable flattened mastering columns in the stable track export projection.

- [ ] **Step 1: Write failing export and schema tests**

Assert all new fields for a current success, blank/null serialization without one, replacement after a newer success, preservation after a newer failure, and target-only DJ projection changes. Confirm legacy `loudness_lufs`, `true_peak_db`, and `dynamic_range` remain unchanged and are not used as fallback values. Assert tracks export schema version 2 in the snapshot manifest and a V2 `$id` in `tracks.schema.json`.

- [ ] **Step 2: Run export tests and observe RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_tracks_export.py tests/test_snapshot.py -q`

Expected: FAIL because the read projection and schema omit mastering fields.

- [ ] **Step 3: Consume the finalized V9 view in the explicit export query**

Task 3 already finalized the V9 view and migration. Do not edit either migration SQL file here. Select the uniquely named fields:

```text
integrated_lufs
loudness_range_lu
true_peak_dbtp
short_term_lufs_p50
short_term_lufs_p95
peak_to_loudness_ratio_db
required_gain_db
available_gain_db
gain_deficit_db
```

Keep the existing legacy technical columns and duplicate fields in their established order. Append the new fields to the public tabular schema to minimize compatibility impact.

- [ ] **Step 4: Update exporter row mapping and versioned JSON Schemas**

Add nullable `number` definitions and stable serialization. Change the tracks schema `$id` to `/schemas/v2/tracks.schema.json`, set `tracks_export_schema_version` to `2` in `SnapshotExporter`, and update its manifest schema constant. Do not change the overall snapshot schema version or unrelated facet versions. Do not hand-edit generated artifacts; modify only source schema/export code and regenerate through an existing project command if any target is generated.

- [ ] **Step 5: Run export GREEN and schema parity**

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_tracks_export.py tests/test_snapshot.py tests/test_catalog_migrations.py -q
cmp src/dj_digger/catalog/sql/catalog-v9.sql schemas/catalog-v9.sql
```

Expected: PASS and byte-identical schema files.

- [ ] **Step 6: Create a scoped commit if explicitly authorized**

Use the project `commit` skill with subject `feat: export mastering and dj metrics`. Its bounded brief must list read/export/snapshot/schema/test files, schema-version and serialization proof, and remaining end-to-end qualification risk.

---

### Task 9: Add public FFmpeg proof, documentation, and final qualification

**Files:**
- Create: `tests/fixtures/mastering/README.md`
- Create: `tests/mastering_fixture.py`
- Create: `tests/test_mastering_integration.py`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `tests/test_requalification_documentation.py`

**Interfaces:**
- Consumes: public CLI, packaged V9 schema, real FFmpeg/Chromaprint, and track exports.
- Produces: reproducible acceptance evidence and user-facing documentation.

- [ ] **Step 1: Write the failing public-composition integration test**

Generate two independent temporary public fixtures using FFmpeg before asserting product behavior:

- an exact-group fixture containing lossless/lossy encodings of one unchanged generated signal, with observed equal complete fingerprints;
- an EBU fixture containing controlled gain/dynamics variants, without assuming they share a fingerprint.

Use the exact-group fixture for real orchestration and export. Use the EBU fixture for real decoded measurement assertions. Seed deterministic public mastering rows through the real repository boundary for group-comparison threshold coverage. Then run the real CLI composition:

```bash
dj-digger scan --config "$TMP_CONFIG"
dj-digger duplicates --analyze --mastering --mark-best-quality --config "$TMP_CONFIG" --json
dj-digger duplicates --list --dj-review --config "$TMP_CONFIG" --json
dj-digger export --facet tracks --config "$TMP_CONFIG"
```

The Python test must invoke the Typer application or installed entry point, not a fake service. Assert SQLite history/projections, output metrics, deterministic sorting, second-run reuse, and unchanged SHA-256 hashes for every source file.

- [ ] **Step 2: Run the integration test and observe relevant RED**

Run: `UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest tests/test_mastering_integration.py -q`

Expected: FAIL on the first missing or incorrect public behavior, not on fixture construction or an unproven transformed-fingerprint assumption.

- [ ] **Step 3: Prove each fixture's stated boundary without weakening identity proof**

Assert that the exact-group fixture is grouped before testing mastering orchestration. Assert known directional EBU differences for the controlled EBU fixture and unchanged source hashes. Keep the three proof claims separate; do not claim a single end-to-end mastering-variant fixture unless exact fingerprint equality is independently observed.

- [ ] **Step 4: Document current versus future behavior**

Document `--mastering`, `--dj-review`, default targets, provisional thresholds, exact-identity limitation, idempotence, timeout cost, partial exit behavior, nullable metrics, calibration workflow, and the explicit deferral of `best_dj_candidate`. Update `docs/ARCHITECTURE.md` only with implemented V9 behavior; retain the design spec as historical design authority.

- [ ] **Step 5: Run focused subsystem QA**

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv run --python 3.12 --with pytest pytest \
  tests/test_mastering_metrics.py tests/test_ebur128.py tests/test_mastering_persistence.py \
  tests/test_mastering_service.py tests/test_mastering_comparison.py \
  tests/test_duplicates_service.py tests/test_duplicate_quality.py \
  tests/test_cli_duplicates.py tests/test_tracks_export.py tests/test_mastering_integration.py -q
```

Expected: PASS.

- [ ] **Step 6: Run full Python 3.12 qualification**

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uv run --python 3.12 --extra analysis --with pytest pytest -q
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx ruff check src tests
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx ruff format --check src tests
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uvx --with typer mypy src
```

Expected: all tests pass, Ruff and formatting are clean, and strict mypy reports no errors.

- [ ] **Step 7: Run catalog, packaging, privacy, and diff gates**

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache uv build
git diff --check
git status --short
```

Inspect the diff for private artist names, track titles, absolute library paths, SQLite files, local configuration, workspaces, sets, generated-only assets, and unrelated changes. Query a temporary V9 database with `PRAGMA foreign_key_check` and confirm zero rows.

- [ ] **Step 8: Create final scoped commits only if explicitly authorized**

Stage exactly the documented source, tests, schemas, and approved documentation. Never stage `config/local.toml`, `workspace/`, `sets/`, SQLite files, or unrelated changes. Include the bounded worker handoff in commit messages as required by the repository contract.

## Acceptance Checklist

- [ ] Integrated LUFS, LRA, True Peak, short-term P50/P95, and PLR are measured and persisted.
- [ ] Required gain, available gain, and gain deficit are persisted in the rebuildable DJ projection.
- [ ] Exact duplicate groups expose signed member deltas, `mastering_variant`, and `dj_review_recommended`.
- [ ] Missing `best_quality` and incomplete analyses are explicit, never false negatives.
- [ ] `duplicates --analyze` remains lightweight; `--mastering` opts into full decode.
- [ ] Current compatible successes are reused; target-only changes never decode audio.
- [ ] Per-track failures are append-only, bounded, visible, and resumable.
- [ ] JSON and tabular exports expose nullable new fields without reinterpreting legacy loudness fields.
- [ ] `QualitySelector`, `RANKING_VERSION`, and technical ranking behavior remain unchanged.
- [ ] Public-path proof uses real FFmpeg and exact fingerprint grouping without touching source bytes.
- [ ] Full pytest, Ruff, format, mypy, migration, schema, packaging, privacy, and diff gates pass.
