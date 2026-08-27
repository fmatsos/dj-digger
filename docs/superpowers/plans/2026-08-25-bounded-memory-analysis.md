# Bounded-Memory Audio Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound DSP memory by one decoded track plus fixed FFT storage, persist each outcome immediately, and recover interrupted runs automatically.

**Architecture:** Keep samples in single precision and replace whole-track spectral matrices with online accumulators. Split aggregate persistence into start/outcome/finalize operations, then process a bounded set of futures and commit each completion. Reconcile stale `running` rows before selecting work for a new run.

**Tech Stack:** Python 3.12, NumPy 2, Essentia, SQLite, `concurrent.futures`, pytest, Ruff, mypy.

---

## File Map

- `src/dj_digger/analysis/rhythm.py`: single-precision adapter contract.
- `src/dj_digger/analysis/extractor.py`: single-precision propagation and streaming FFT.
- `src/dj_digger/analysis/persistence.py`: incremental run lifecycle and recovery.
- `src/dj_digger/analysis/pipeline.py`: bounded futures and immediate commits.
- `tests/test_extractor.py`: dtype, equivalence, and retention regressions.
- `tests/test_analysis_persistence.py`: lifecycle, atomicity, and recovery regressions.
- `tests/test_analysis_pipeline.py`: immediate visibility, concurrency, reuse, and statuses.
- `tests/docker_analysis_smoke.py`: single-precision real-Essentia smoke.

### Task 1: Preserve single precision through extraction

**Files:**
- Modify: `tests/test_extractor.py`
- Modify: `src/dj_digger/analysis/rhythm.py`
- Modify: `src/dj_digger/analysis/extractor.py`
- Modify: `tests/docker_analysis_smoke.py`

- [ ] **Step 1: Write the failing propagation test**

Add a recording rhythm double and assert observable dtype:

```python
class _RecordingRhythm(_Rhythm):
    def __init__(self) -> None:
        self.samples: np.ndarray | None = None

    def analyze(self, samples: object, rate: int) -> RhythmFacts:
        assert isinstance(samples, np.ndarray)
        self.samples = samples
        return super().analyze(samples, rate)


def test_composite_keeps_decoded_samples_in_single_precision(tmp_path: Path) -> None:
    rhythm = _RecordingRhythm()
    CompositeAudioExtractor(
        decoder=_Decoder(), probe=_Probe(), rhythm=rhythm,
        spectrum=_Spectrum(), planner=_Planner(),
    ).extract(tmp_path / "track.wav")
    assert rhythm.samples is not None
    assert rhythm.samples.dtype == np.float32
```

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_extractor.py::test_composite_keeps_decoded_samples_in_single_precision -q`.
Expected: FAIL because the current composite passes `float64`.

- [ ] **Step 3: Implement minimal dtype changes**

Use `Samples = NDArray[np.float32]` in `rhythm.py`. Pass `samples` directly to
`self._rhythm.analyze(samples, 48_000)` in the composite. Remove the explicit double conversion
from `tests/docker_analysis_smoke.py`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
pytest tests/test_extractor.py::test_composite_keeps_decoded_samples_in_single_precision -q
rg -n 'samples\.astype\(|asarray\(samples, dtype=np\.float64' src tests
```

Expected: PASS and no forbidden full-track conversion in the analysis path.

### Task 2: Stream spectral aggregation

**Files:**
- Modify: `tests/test_extractor.py`
- Modify: `src/dj_digger/analysis/extractor.py`

- [ ] **Step 1: Write reference-equivalence tests**

Add a test-only implementation of the old matrix formula and compare all results for normal,
short, and non-hop-aligned signals:

```python
@pytest.mark.parametrize("size", [5, 32, 65])
def test_numpy_spectrum_stream_matches_matrix_reference(size: int) -> None:
    config = _spectrum_config()
    samples = np.sin(np.arange(size, dtype=np.float32))
    expected = _matrix_spectrum_reference(samples, config, 8, 4, 48_000)
    actual = NumpySpectrumAdapter(config, 8, 4).extract(samples, 48_000)
    assert actual == pytest.approx(expected, rel=1e-6, abs=1e-9)
```

- [ ] **Step 2: Write the failing bounded-retention test**

Monkeypatch `np.fft.rfft` to return a weak-referenceable ndarray subclass. Run garbage
collection before each FFT and assert at most two previous FFT arrays remain live. The old
`spectra` list must make this test fail on a long synthetic signal.

- [ ] **Step 3: Verify RED**

Run `pytest tests/test_extractor.py -k 'stream_matches or does_not_retain' -q`.
Expected: retention FAIL because all spectra are retained.

- [ ] **Step 4: Implement online aggregation**

Keep `values = np.asarray(samples, dtype=np.float32)` and a single-precision Hann window.
Replace `spectra`, `matrix`, and `diff(matrix)` with:

```python
magnitude_sum = np.zeros(self._window_size // 2 + 1, dtype=np.float64)
previous_magnitude: np.ndarray | None = None
flux_sum = 0.0
flux_count = 0
frame_count = 0
for start in range(0, values.size - self._window_size + 1, self._hop_size):
    magnitude = np.abs(np.fft.rfft(values[start:start + self._window_size] * window))
    magnitude_sum += magnitude
    if previous_magnitude is not None:
        positive = np.maximum(magnitude - previous_magnitude, 0.0)
        flux_sum += float(positive.sum())
        flux_count += positive.size
    previous_magnitude = magnitude
    frame_count += 1
power = magnitude_sum / frame_count
```

The only `float64` allocation allowed here is fixed-size FFT accumulation, never track-sized.
Set onset to `flux_sum / flux_count` or zero. Preserve band and centroid formulas.

- [ ] **Step 5: Verify GREEN**

Run `pytest tests/test_extractor.py -q`. Expected: all extractor tests PASS.

### Task 3: Add incremental persistence and recovery

**Files:**
- Modify: `tests/test_analysis_persistence.py`
- Modify: `src/dj_digger/analysis/persistence.py`

- [ ] **Step 1: Write failing lifecycle tests**

Exercise this API and assert rows, sections, events, counters, and status:

```python
run_id = persistence.start_run(ident, eligible=2, reused=0, started_at="start")
persistence.persist_outcome(
    run_id, ident, AnalysisOutcome(track, {"bpm": 128.0}, None, "aggregation"),
    occurred_at="one",
)
assert database.execute(
    "SELECT status, analyzed, failed FROM analysis_runs WHERE id = ?", (run_id,)
).fetchone() == ("running", 1, 0)
assert persistence.finish_run(run_id, finished_at="finish") == ("partial", 1, 0)
```

Add abandoned-run cases: all work accounted/no failures -> `succeeded`; success plus
unaccounted work -> `partial`; reuse plus failure -> `partial`; no success/reuse -> `failed`.
Assert reconciliation is idempotent and creates no new attempt/event.

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_analysis_persistence.py -k 'lifecycle or reconcile' -q`.
Expected: FAIL because lifecycle methods do not exist.

- [ ] **Step 3: Implement lifecycle methods**

Add these exact public method contracts: `start_run(self, identity: AnalysisIdentity, *,
eligible: int, reused: int, started_at: str) -> int`; `persist_outcome(self, run_id: int,
identity: AnalysisIdentity, outcome: Outcome, *, occurred_at: str) -> tuple[int, int]`;
`finish_run(self, run_id: int, *, finished_at: str) -> tuple[str, int, int]`; and
`reconcile_running_runs(self, *, finished_at: str) -> int`.

Each outcome transaction inserts attempt/sections/event and increments exactly one aggregate
counter. Derive status from `eligible`, `analyzed`, `reused`, `failed`, treating unaccounted
eligible work as interruption. Factor insertion into a transaction-neutral private helper used
only by the current lifecycle.

- [ ] **Step 4: Verify GREEN**

Run `pytest tests/test_analysis_persistence.py -q`. Expected: all tests PASS.

### Task 4: Bound pipeline concurrency and commit completions

**Files:**
- Modify: `tests/test_analysis_pipeline.py`
- Modify: `src/dj_digger/analysis/pipeline.py`

- [ ] **Step 1: Write the failing immediate-visibility test**

With two tracks and `workers=1`, open a separate SQLite connection while extracting the second
track and assert the first attempt is already committed:

```python
if track.relative_path.endswith("B.flac"):
    observer = sqlite3.connect(tmp_path / "catalog.sqlite")
    try:
        assert observer.execute("SELECT COUNT(*) FROM audio_analysis").fetchone()[0] == 1
    finally:
        observer.close()
```

- [ ] **Step 2: Write the bounded-concurrency test**

Use a lock-protected active counter and event barrier with four tracks and `workers=2`. Assert
`peak_active == 2`, release with a timeout, then assert four attempts and a succeeded run.

- [ ] **Step 3: Write interrupted-run reuse test**

Create a `running` run with one persisted success, start a new pipeline, and assert the old run
becomes `partial`, the successful track is not extracted again, and the remaining track succeeds.

- [ ] **Step 4: Verify RED**

Run `pytest tests/test_analysis_pipeline.py -k 'immediately or bounded or interrupted' -q`.
Expected: immediate visibility and recovery FAIL under aggregate-list persistence.

- [ ] **Step 5: Implement bounded futures**

Reconcile old runs before selecting pending work. Open the new aggregate run, submit at most
`workers` futures, wait with `FIRST_COMPLETED`, persist each outcome, then submit replacements.
Do not retain committed outcomes. Preserve `AnalysisExtractionError.stage` normalization.
Finalize the run and return its persisted status/counters.

- [ ] **Step 6: Verify GREEN and public contracts**

Run:

```bash
pytest tests/test_analysis_pipeline.py tests/test_application_contracts.py tests/test_cli_analyze.py -q
```

Expected: all targeted tests PASS.

### Task 5: Complete verification

**Files:**
- Verify only; preserve user-owned `config/local.toml`, `sets/`, `workspace/`, and `references/copy-set.sh`.

- [ ] **Step 1: Run unit and static verification**

```bash
pytest -q
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools uvx ruff check src tests
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools uvx --with typer mypy src
git diff --check
```

Expected: pytest PASS with documented skips; Ruff and mypy PASS; diff check silent.

- [ ] **Step 2: Run Docker analysis smoke**

Run the existing repository command targeting `tests/docker_analysis_smoke.py` under Python
3.12 with Essentia and FFmpeg. Expected: PASS without dtype-truncation warnings.

- [ ] **Step 3: Measure bounded real audio**

Run the existing local-library acceptance harness with `/usr/bin/time -v` and
`DJ_DIGGER_LIBRARY_ROOT`. Report only counts and maximum RSS, never private paths or filenames.
Expected: completed persisted outcomes and peak RSS materially below the observed 4 GiB OOM.

- [ ] **Step 4: Inspect scope**

```bash
git status --short
git diff -- src/dj_digger/analysis tests
```

Expected: only intended implementation/tests plus local untracked spec/plan; existing user
changes untouched. Do not stage or commit `docs/superpowers/specs/*` or
`docs/superpowers/plans/*`.

### Task 6: Remove all legacy compatibility

**Files:**
- Delete legacy persistence APIs/tests from `src/dj_digger/analysis/persistence.py` and callers.
- Consolidate `src/dj_digger/catalog/sql/catalog-v1.sql` through `catalog-v5.sql` into one
  current schema resource and make `src/dj_digger/catalog/migrations.py` reject old versions.
- Delete `src/dj_digger/exports/legacy.py` and `LegacyExportRepository`.
- Remove `ExportConfig.legacy_compatibility`, `[export]` support, and conditional legacy export
  orchestration from configuration/application/audit code.
- Delete or rewrite all legacy-specific tests, fixtures, schemas, and documentation references.

- [ ] **Step 1: Write RED contracts** proving an empty database receives the consolidated current
  schema, an old-version database is rejected, old `[export]` configuration is rejected, and
  canonical export no longer publishes historical facets.
- [ ] **Step 2: Run the focused tests and observe failures** caused by the still-present legacy
  paths.
- [ ] **Step 3: Remove the persistence compatibility surface** while retaining only
  `start_run`, `persist_outcome`, `finish_run`, and `reconcile_running_runs` plus their private
  current helpers.
- [ ] **Step 4: Replace migrations with the consolidated fresh schema** and an explicit version
  guard that refuses all historical catalog versions with a recreation message.
- [ ] **Step 5: Remove legacy exporters/repositories/configuration** and update canonical callers.
- [ ] **Step 6: Remove obsolete tests/resources/docs references**, then run focused tests, the
  complete Python 3.12 suite, Ruff, mypy, Docker smoke, and `git diff --check`.
