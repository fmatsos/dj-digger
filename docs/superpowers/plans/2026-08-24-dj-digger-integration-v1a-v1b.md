# DJ Digger Unified V1A/V1B Integration and Acceptance Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove functional parity with the historical audit exporter, verify historical/failure semantics and DSP reuse on real data, then cut first-party consumers over to `tracks.tsv` without breaking set-copy paths.

**Architecture:** Acceptance uses deterministic fixtures first, then a controlled representative subset, then the real-library regression. Old and new outputs are compared only at public contracts; implementation details such as scan count and SQLite history are validated independently. V1B is accepted only with legacy inventory facets disabled.

**Tech Stack:** pytest; shell fixture harnesses; SQLite inspection; JSON Schema validation; existing `copy-set.sh` in read-only source mode.

**Spec:** `docs/superpowers/specs/2026-08-24-dj-digger-unified-v1-design.md`

## Global Constraints

- Never run destructive commands against the source media library.
- Historical `export-music-audit.sh` is reference-only and may be run solely to create comparison output.
- A failed scan must never produce missing transitions.
- V1A comparison must account for documented serialization normalization only.
- V1B acceptance runs with legacy inventory facet generation disabled.

---

### Task 1: Build a parity fixture covering every historical audit category

**Files:**
- Create: `tests/fixtures/parity-library/`
- Create: `tests/integration/test_audit_parity.py`

**Interfaces:**
- Fixture contains audio formats, tags, empty directories, Traktor, Serato, M3U/M3U8/PLS/CUE/XML/DB artifacts.

- [ ] **Step 1: Write failing fixture coverage assertions**

```python
EXPECTED = {"audio", "empty_directory", "traktor", "serato", "playlist", "cue", "xml", "database"}
assert fixture_categories(PARITY_LIBRARY) == EXPECTED
```

- [ ] **Step 2: Run integration test**

```bash
pytest tests/integration/test_audit_parity.py -q
```
Expected: FAIL until fixture is complete.

- [ ] **Step 3: Generate deterministic fixture files and tag metadata**

Use generated short audio files and tiny representative metadata files; do not depend on the user's real library for contract tests.

- [ ] **Step 4: Run fixture coverage test**

```bash
pytest tests/integration/test_audit_parity.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/parity-library tests/integration/test_audit_parity.py
git commit -m "test: add historical audit parity fixture"
```

### Task 2: Compare V1A catalog-derived facets with historical exporter contracts

**Files:**
- Modify: `tests/integration/test_audit_parity.py`
- Reference: `references/export-music-audit.sh`

**Interfaces:**
- Compares path sets, five-column inventory values, metadata coverage, directory/stat counts and artifact discovery.

- [ ] **Step 1: Add failing old-vs-new assertions**

```python
assert new_inventory_paths == old_inventory_paths
assert new_directory_paths == old_directory_paths
assert new_artifact_paths == old_artifact_paths
assert normalized_legacy_rows(new_rows) == normalized_legacy_rows(old_rows)
```

- [ ] **Step 2: Run comparison**

```bash
pytest tests/integration/test_audit_parity.py -q
```
Expected: FAIL on any unimplemented historical facet.

- [ ] **Step 3: Fix only documented contract gaps**

Allowed normalization is limited to implementation-independent formatting explicitly frozen by the spec; do not hide missing files/metadata behind loose comparison logic.

- [ ] **Step 4: Re-run parity test**

```bash
pytest tests/integration/test_audit_parity.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_audit_parity.py
git commit -m "test: prove audit exporter functional parity"
```

### Task 3: Prove scan failure, missing and restoration history end-to-end

**Files:**
- Create: `tests/integration/test_scan_history.py`

**Interfaces:**
- Exercises actual CLI + SQLite state across multiple scans.

- [ ] **Step 1: Write failing scenario test**

```python
scan_ok(["A.flac", "B.flac"])
scan_fail_after_observing(["A.flac"])
assert status("B.flac") == "present"
scan_ok(["A.flac"])
assert status("B.flac") == "missing"
restore("B.flac")
scan_ok(["A.flac", "B.flac"])
assert events("B.flac")[-2:] == ["missing", "restored"]
```

- [ ] **Step 2: Run test**

```bash
pytest tests/integration/test_scan_history.py -q
```
Expected: FAIL until full orchestration matches lifecycle rules.

- [ ] **Step 3: Fix orchestration/transaction boundaries without weakening assertions**

Do not implement retries that convert an incomplete traversal into a successful scan.

- [ ] **Step 4: Re-run test**

```bash
pytest tests/integration/test_scan_history.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_scan_history.py src
git commit -m "test: verify historical scan lifecycle end to end"
```

### Task 4: Validate V1A analysis reuse and snapshot publication on a representative subset

**Files:**
- Create: `tests/integration/test_v1a_pipeline.py`

**Interfaces:**
- Runs `refresh`, second `analyze`, and `snapshot --archive`.

- [ ] **Step 1: Write failing pipeline assertions**

```python
first = refresh(subset)
second = analyze(subset)
assert second.reused == second.eligible
snapshot = create_snapshot()
assert snapshot.archive.exists()
assert validate_snapshot(snapshot)
```

- [ ] **Step 2: Run test**

```bash
pytest tests/integration/test_v1a_pipeline.py -q
```
Expected: FAIL until all V1A workstreams are integrated.

- [ ] **Step 3: Resolve integration defects without schema drift**

The accepted schemas in `schema-bundle.json` are fixed for this milestone; behavior fixes must conform to them.

- [ ] **Step 4: Re-run test**

```bash
pytest tests/integration/test_v1a_pipeline.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_v1a_pipeline.py src
git commit -m "test: accept unified V1A pipeline"
```

### Task 5: Run controlled real-library V1A parity pilot

**Files:**
- Create: `docs/acceptance/v1a-real-library-pilot.md`
- Add: non-sensitive generated result summaries only

**Interfaces:**
- Pilot subset is manually selected and source library remains read-only.

- [ ] **Step 1: Record pre-run source counts and checksums for the chosen subset**

```bash
dj-digger scan --source djing --config ./dj-digger.toml
sqlite3 ./dj-digger.sqlite 'select count(*) from tracks where source_id="djing" and presence_status="present";'
```

- [ ] **Step 2: Run V1A refresh and snapshot**

```bash
dj-digger refresh --config ./dj-digger.toml
dj-digger snapshot --config ./dj-digger.toml --output ./acceptance --archive
```
Expected: successful scans, schema-valid facets, no source mutations.

- [ ] **Step 3: Compare historical and compatibility path sets**

```bash
python tools/compare_legacy_inventory.py old/djing-files.tsv acceptance/latest/djing-files.tsv
```
Expected: identical path set; any formatting delta documented and justified.

- [ ] **Step 4: Record acceptance findings**

Document counts for present/missing, metadata failures, analysis failures/reuse, artifact counts, snapshot hash validation and any known non-blocking differences.

- [ ] **Step 5: Commit acceptance report**

```bash
git add docs/acceptance/v1a-real-library-pilot.md
git commit -m "docs: record V1A real-library acceptance"
```

### Task 6: Cut V1B first-party consumers to `tracks.tsv` and disable legacy inventory facets

**Files:**
- Create: `tests/integration/test_v1b_cutover.py`
- Modify: test config to disable legacy facets

**Interfaces:**
- Curator and first-party tooling run with no `djing-files.tsv`/`music-files.tsv` present.

- [ ] **Step 1: Write failing no-legacy test**

```python
workspace = refresh_with_legacy_facets(enabled=False)
assert not (workspace / "djing-files.tsv").exists()
result = generate_known_set(workspace / "tracks.tsv")
assert result.valid
```

- [ ] **Step 2: Run test**

```bash
pytest tests/integration/test_v1b_cutover.py -q
```
Expected: FAIL while any first-party dependency remains.

- [ ] **Step 3: Remove remaining first-party dependency or fixture assumption**

Do not delete the compatibility exporter itself; V1B deprecates it but allows operators to enable it.

- [ ] **Step 4: Re-run V1B cut-over test**

```bash
pytest tests/integration/test_v1b_cutover.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: accept tracks.tsv first-party cutover"
```

### Task 7: Verify `copy-set.sh` compatibility and known Acid Rave regression

**Files:**
- Create: `tests/integration/test_copy_set_compatibility.py`
- Create/update: known-set golden fixture

**Interfaces:**
- Generated M3U8 paths are source-relative and resolve under the explicit library root.

- [ ] **Step 1: Write failing path-resolution test**

```python
for path in parse_m3u8(generated_playlist):
    assert (library_root / path).is_file()
```

- [ ] **Step 2: Run regression before invoking copy script**

```bash
pytest tests/integration/test_copy_set_compatibility.py -q
```
Expected: FAIL on any absolute/ambiguous/mutated path.

- [ ] **Step 3: Run the external copy script against a temporary output directory**

```bash
copy-set.sh --library "$FIXTURE_LIBRARY" --output "$TMPDIR/set" --playlist "$GENERATED_M3U8"
```
Expected: every selected track copied from the intended source; source files remain unchanged.

- [ ] **Step 4: Run complete acceptance gate**

```bash
pytest -q
ruff check .
mypy src
python tests/validate_fixtures.py
```
Expected: PASS with legacy inventory facets disabled for first-party tests.

- [ ] **Step 5: Commit**

```bash
git add tests docs
git commit -m "test: complete unified V1B acceptance"
```
