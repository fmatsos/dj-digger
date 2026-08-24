# DJ Digger Integrated Audio Analysis V1A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all planned DJ audio analysis into `dj-digger`, using catalog identities and historical analysis rows instead of an external inventory TSV and destructive SQLite cache.

**Architecture:** Analysis eligibility is a repository query over `present` tracks from sources with `analyze=true`. FFmpeg owns technical facts, DSP stages own musical facts, and successful results are immutable/versioned rows keyed by track facts plus analysis identity. Exporters project the latest applicable result to source-aware V2 analysis contracts.

**Tech Stack:** Python 3.12; SQLite; FFmpeg; Essentia; librosa; NumPy; SciPy; jsonschema; pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-dj-digger-unified-v1-design.md`

## Global Constraints

- No `--inventory` input and no `AnalysisCache.prune()` abstraction.
- Analysis schema version is `2` because `source_id` and `track_id` are required public fields.
- Reuse identity is `(track_id, input_size_bytes, input_mtime_ns, analysis_schema_version, analyzer_version, config_hash)`.
- Missing tracks retain historical analysis.
- Restored unchanged files may reuse matching historical analysis.
- Per-track analysis failures do not abort unrelated tracks.
- Fixed windows remain beat-synchronous 8/16/32/64 bars and are emitted only when stable bars exist.
- Semantic labels below confidence `0.80` are `null`.

---

## Target file map

```text
src/dj_digger/analysis/
├── config.py
├── eligibility.py
├── ffmpeg.py
├── audio.py
├── rhythm.py
├── spectrum.py
├── windows.py
├── segmentation.py
├── semantics.py
├── aggregation.py
├── persistence.py
├── exporters.py
└── pipeline.py
```

### Task 1: Replace external inventory/cache logic with catalog-backed eligibility

**Files:**
- Create: `src/dj_digger/analysis/eligibility.py`, `config.py`
- Modify: `src/dj_digger/catalog/repositories.py`
- Test: `tests/test_analysis_eligibility.py`

**Interfaces:**
- Produces: `AnalysisIdentity(schema_version: int, analyzer_version: str, config_hash: str)`
- Produces: `AnalysisEligibility.pending(identity: AnalysisIdentity, source_id: str | None = None, path_prefix: str | None = None) -> list[Track]`

- [ ] **Step 1: Write failing reuse/changed/missing tests**

```python
def test_pending_excludes_exact_reusable_analysis(catalog) -> None:
    track = present_track(catalog, size=10, mtime_ns=20)
    successful_analysis(track, size=10, mtime_ns=20, schema=2, version="1.0.0", config_hash=HASH)
    assert eligibility.pending(identity) == []

def test_missing_track_is_not_pending_but_analysis_remains(catalog) -> None:
    track = missing_track_with_analysis(catalog)
    assert eligibility.pending(identity) == []
    assert catalog.analysis_history(track.id)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_analysis_eligibility.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement repository query using current file facts and source config**

```sql
SELECT t.*
FROM tracks t
JOIN library_sources s ON s.source_id = t.source_id
LEFT JOIN audio_analysis a ON a.track_id = t.id
  AND a.input_size_bytes = t.size_bytes
  AND a.input_mtime_ns = t.mtime_ns
  AND a.analysis_schema_version = :schema
  AND a.analyzer_version = :version
  AND a.config_hash = :config_hash
  AND a.analysis_status = 'succeeded'
WHERE t.presence_status = 'present' AND s.enabled = 1 AND s.analyze = 1 AND a.id IS NULL
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_analysis_eligibility.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/analysis/eligibility.py src/dj_digger/analysis/config.py src/dj_digger/catalog/repositories.py tests/test_analysis_eligibility.py
git commit -m "feat: derive analysis eligibility from catalog"
```

### Task 2: Implement FFmpeg technical metadata as the canonical technical producer

**Files:**
- Create: `src/dj_digger/analysis/ffmpeg.py`, `audio.py`
- Modify: `src/dj_digger/catalog/repositories.py`
- Test: `tests/test_ffmpeg.py`

**Interfaces:**
- Produces: `FFmpegProbe.probe(path: Path) -> TechnicalAudioMetadata`

- [ ] **Step 1: Write failing probe ownership test**

```python
def test_ffmpeg_normalizes_technical_facts(audio_fixture: Path) -> None:
    meta = probe.probe(audio_fixture)
    assert meta.duration_seconds > 0
    assert meta.sample_rate == 48000
    assert meta.codec
    assert meta.container
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_ffmpeg.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement read-only ffprobe/ffmpeg invocation and persistence**

```python
cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
```
Add loudness/true-peak/dynamic-range extraction without writing source files.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_ffmpeg.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/analysis/ffmpeg.py src/dj_digger/analysis/audio.py tests/test_ffmpeg.py
git commit -m "feat: add canonical FFmpeg technical probing"
```

### Task 3: Port deterministic rhythm/key extraction

**Files:**
- Create: `src/dj_digger/analysis/rhythm.py`
- Test: `tests/test_rhythm.py`

**Interfaces:**
- Produces: `RhythmAnalyzer.analyze(samples: NDArray, sample_rate: int) -> RhythmFacts`

- [ ] **Step 1: Write failing BPM/key fixture test**

```python
def test_rhythm_facts_are_within_fixture_tolerance(acid_loop) -> None:
    facts = analyzer.analyze(acid_loop.samples, acid_loop.sample_rate)
    assert facts.bpm == pytest.approx(145.0, abs=0.5)
    assert 0.0 <= facts.bpm_confidence <= 1.0
    assert 0.0 <= facts.beat_stability <= 1.0
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_rhythm.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement pinned Essentia rhythm/key adapters**

```python
@dataclass(frozen=True)
class RhythmFacts:
    bpm: float | None
    bpm_confidence: float
    beat_positions: tuple[float, ...]
    beat_stability: float
    key: str | None
    key_confidence: float
```
No semantic section labels are produced here.

- [ ] **Step 4: Run deterministic repeated-run test**

```bash
pytest tests/test_rhythm.py -q
```
Expected: PASS within frozen tolerances.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/analysis/rhythm.py tests/test_rhythm.py
git commit -m "feat: extract deterministic rhythm and key facts"
```

### Task 4: Port spectral/low-end facts and beat-synchronous windows

**Files:**
- Create: `src/dj_digger/analysis/spectrum.py`, `windows.py`
- Test: `tests/test_spectrum.py`, `tests/test_windows.py`

**Interfaces:**
- Produces normalized sub/low/low-mid/kick/bass/onset/spectral facts.
- Produces intro/outro windows for 8/16/32/64 stable bars.

- [ ] **Step 1: Write failing spectral and insufficient-bars tests**

```python
def test_short_track_does_not_fake_64_bar_window(short_track) -> None:
    windows = analyzer.windows(short_track)
    assert windows.intro_64.available is False
    assert windows.outro_64.available is False
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_spectrum.py tests/test_windows.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement frequency-band aggregation and stable beat anchoring**

```python
WINDOW_BARS = (8, 16, 32, 64)

def available_window(beats: Sequence[float], bars: int, beats_per_bar: int = 4) -> bool:
    return len(beats) >= bars * beats_per_bar + 1
```
Thresholds/frequency bands come only from versioned `analysis.toml`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_spectrum.py tests/test_windows.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/analysis/spectrum.py src/dj_digger/analysis/windows.py tests/test_spectrum.py tests/test_windows.py
git commit -m "feat: analyze low end and DJ windows"
```

### Task 5: Port structural segmentation and confidence-gated semantics

**Files:**
- Create: `src/dj_digger/analysis/segmentation.py`, `semantics.py`
- Test: `tests/test_segmentation.py`, `tests/test_semantics.py`

**Interfaces:**
- Produces: `Segmenter.segment(...) -> tuple[TrackSection, ...]`
- Produces semantic label only at confidence `>= 0.80`.

- [ ] **Step 1: Write failing boundary/label tests**

```python
def test_low_confidence_semantic_is_null(section_facts) -> None:
    semantic = semantics.classify(section_facts)
    if semantic.confidence < 0.80:
        assert semantic.label is None
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_segmentation.py tests/test_semantics.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement deterministic structural facts first, semantics second**

```python
section = TrackSection(
    start_seconds=start,
    end_seconds=end,
    facts=aggregate_facts(...),
    derived=derive_flags(...),
    semantic=classify_semantics(...),
)
```
Semantic labels never alter section boundaries or factual metrics.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_segmentation.py tests/test_semantics.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/analysis/segmentation.py src/dj_digger/analysis/semantics.py tests/test_segmentation.py tests/test_semantics.py
git commit -m "feat: add structural DJ section analysis"
```

### Task 6: Persist immutable versioned analyses and track failures/events

**Files:**
- Create: `src/dj_digger/analysis/persistence.py`, `aggregation.py`
- Modify: `src/dj_digger/catalog/repositories.py`
- Test: `tests/test_analysis_persistence.py`

**Interfaces:**
- Produces: `AnalysisPersistence.store_success(...) -> int`
- Produces: `AnalysisPersistence.store_failure(...) -> None`

- [ ] **Step 1: Write failing history retention test**

```python
def test_new_config_keeps_previous_analysis(catalog) -> None:
    old_id = persist_success(track, config_hash=HASH_A)
    new_id = persist_success(track, config_hash=HASH_B)
    assert old_id != new_id
    assert [a.config_hash for a in catalog.analysis_history(track.id)] == [HASH_A, HASH_B]
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_analysis_persistence.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement immutable row insertion and event emission**

```python
analysis_id = analyses.insert(result, identity, input_facts)
events.append(track.id, "analysis_completed", analysis_run_id=run_id, payload={"analysis_id": analysis_id})
```
Failures emit `analysis_failed` and do not delete prior successes.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_analysis_persistence.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/analysis/persistence.py src/dj_digger/analysis/aggregation.py src/dj_digger/catalog/repositories.py tests/test_analysis_persistence.py
git commit -m "feat: retain versioned analysis history"
```

### Task 7: Publish source-aware analysis facets and run audit

**Files:**
- Create: `src/dj_digger/analysis/exporters.py`
- Copy: `schemas/dj-analysis.schema.json`, `dj-sections.schema.json`, `dj-analysis-run.schema.json`
- Test: `tests/test_analysis_exporters.py`

**Interfaces:**
- Produces `dj-analysis.tsv`, `dj-sections.jsonl`, `dj-analysis-run.json`.

- [ ] **Step 1: Write failing schema/source identity test**

```python
def test_analysis_export_contains_source_and_track_identity(tmp_path: Path) -> None:
    row = export_and_read_analysis(tmp_path)[0]
    assert row["source_id"] == "djing"
    assert int(row["track_id"]) > 0
    assert row["path"] == "Techno/A.flac"
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_analysis_exporters.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement schema V2 projection and atomic validation**

```python
row = {"source_id": track.source_id, "track_id": track.id, "path": track.relative_path, **analysis_payload}
```
`dj-analysis-run.json` uses `eligible/analyzed/reused/failed`; there is no `cached/pruned` vocabulary.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_analysis_exporters.py -q
```
Expected: PASS against all three V2 analysis schemas.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/analysis/exporters.py schemas/dj-analysis*.json schemas/dj-sections.schema.json tests/test_analysis_exporters.py
git commit -m "feat: publish source-aware analysis facets"
```

### Task 8: Wire `analyze` and complete `refresh` integration

**Files:**
- Create: `src/dj_digger/analysis/pipeline.py`
- Modify: `src/dj_digger/application.py`, `src/dj_digger/cli.py`
- Test: `tests/test_analysis_pipeline.py`, `tests/test_cli_analyze.py`

**Interfaces:**
- `dj-digger analyze [--source ID] [--path PREFIX] [--limit N] [--force] [--workers N]`
- `refresh` invokes analysis only after scan/metadata phases.

- [ ] **Step 1: Write failing incremental CLI test**

```python
def test_second_analyze_run_reuses_unchanged_tracks(runner) -> None:
    first = runner.invoke(app, ["analyze", "--config", FIXTURE_CONFIG])
    second = runner.invoke(app, ["analyze", "--config", FIXTURE_CONFIG])
    assert first.exit_code == second.exit_code == 0
    assert read_last_run()["reused"] == read_last_run()["eligible"]
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_analysis_pipeline.py tests/test_cli_analyze.py -q
```
Expected: FAIL.

- [ ] **Step 3: Implement bounded worker pipeline and force semantics**

```python
tracks = eligibility.pending(identity, source_id=source, path_prefix=path)
if force:
    tracks = eligibility.all_eligible(source_id=source, path_prefix=path)
tracks = tracks[:limit] if limit is not None else tracks
```
Workers process tracks independently; persistence is serialized or transaction-safe.

- [ ] **Step 4: Run full analysis quality gate**

```bash
pytest tests/test_analysis_* tests/test_ffmpeg.py tests/test_rhythm.py tests/test_spectrum.py tests/test_windows.py tests/test_segmentation.py tests/test_semantics.py -q
ruff check .
mypy src
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dj_digger/analysis src/dj_digger/application.py src/dj_digger/cli.py tests
git commit -m "feat: integrate audio analysis into DJ Digger"
```
