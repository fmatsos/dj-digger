# Electronic DJ Set Curator V1A → V1B Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve current set-curation behavior during V1A, then migrate all first-party availability/path logic to the canonical `tracks.tsv` contract while making set artifacts source-aware.

**Architecture:** The skill continues to treat local availability as a hard constraint. V1A supports the legacy inventory facet while source-aware analysis V2 lands; V1B changes source precedence to `tracks.tsv`, filters `set_eligible=true`, carries `source_id/track_id` through candidate/transition/set models, and preserves source-relative M3U8 paths for the external copy workflow.

**Tech Stack:** Markdown skill assets; Python fixture validators; JSON Schema Draft 2020-12.

**Spec:** `docs/superpowers/specs/2026-08-24-dj-digger-unified-v1-design.md`

## Global Constraints

- Availability is never inferred from model/web knowledge.
- V1B availability authority is `tracks.tsv` only.
- A selectable V1B row must be present by virtue of export membership and `set_eligible=true`.
- Exact `path` is preserved verbatim in M3U8.
- `.set.json` schema version is `2` and stores `source_id` + `track_id` per track/alternative.
- Ambiguous identical relative paths across sources must fail validation rather than silently select one.
- Hard constraints remain non-compensable; technical uncertainty remains explicit.

---

### Task 1: Update shared schemas/fixtures for source-aware analysis without changing V1A availability

**Files:**
- Copy: `schemas/*.json`, `schema-bundle.json`
- Modify: `tests/fixtures/dj-analysis.tsv`, `dj-sections.jsonl`, `dj-analysis-run.json`
- Test: `tests/validate_fixtures.py`

**Interfaces:**
- V1A availability input remains `djing-files.tsv`.
- Analysis joins use `source_id`, `track_id`, and `path`.

- [ ] **Step 1: Write failing V2 analysis fixture assertions**

```python
assert bundle["analysis_schema_version"] == 2
assert analysis_rows[0]["source_id"] == "djing"
assert int(analysis_rows[0]["track_id"]) > 0
```

- [ ] **Step 2: Run validator**

```bash
python tests/validate_fixtures.py
```
Expected: FAIL on old fixture/schema versions.

- [ ] **Step 3: Migrate fixtures and source-contract reference**

Keep V1A precedence explicit:

```text
1. djing-files.tsv — current compatibility availability authority
2. dj-analysis.tsv / dj-sections.jsonl — source-aware technical facts
3. dj-analysis-run.json — audit/staleness
```

- [ ] **Step 4: Run validator**

```bash
python tests/validate_fixtures.py
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add schemas schema-bundle.json tests skills/electronic-dj-set-curator/references/source-contracts.md
git commit -m "chore: migrate curator analysis contracts"
```

### Task 2: Preserve compatibility engine and hard-constraint behavior under source-aware identities

**Files:**
- Modify: `skills/electronic-dj-set-curator/references/compatibility-engine.md`
- Modify: `tests/test_golden_set.py`

**Interfaces:**
- Candidate key changes from `path` to `(source_id, track_id)`; `path` remains display/filesystem contract.

- [ ] **Step 1: Write failing collision test**

```python
def test_same_relative_path_in_two_sources_is_not_same_candidate() -> None:
    a = Candidate(source_id="djing", track_id=1, path="Acid/A.flac")
    b = Candidate(source_id="archive", track_id=9, path="Acid/A.flac")
    assert candidate_key(a) != candidate_key(b)
```

- [ ] **Step 2: Run golden tests**

```bash
pytest tests/test_golden_set.py -q
```
Expected: FAIL until identity is migrated.

- [ ] **Step 3: Update documented pseudocode/fixtures**

```python
def candidate_key(c):
    return (c.source_id, c.track_id)
```
Do not alter the seven transition strategy enums, confidence gating, narrative curve, or non-compensable hard constraints.

- [ ] **Step 4: Run golden tests**

```bash
pytest tests/test_golden_set.py -q
```
Expected: PASS with ordering/transition classifications unchanged except identity fields.

- [ ] **Step 5: Commit**

```bash
git add skills/electronic-dj-set-curator/references/compatibility-engine.md tests/test_golden_set.py
git commit -m "refactor: make set candidates source aware"
```

### Task 3: Migrate `.set.json` to schema version 2

**Files:**
- Copy: `schemas/dj-set.schema.json`
- Modify: set-emission reference and fixtures
- Test: `tests/test_set_schema.py`

**Interfaces:**
- Every track/alternative stores `source_id`, `track_id`, `path`.

- [ ] **Step 1: Write failing set-schema test**

```python
def test_set_track_requires_source_identity() -> None:
    payload = fixture_set()
    del payload["tracks"][0]["source_id"]
    with pytest.raises(ValidationError):
        validate_set(payload)
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_set_schema.py -q
```
Expected: FAIL until schema/fixtures migrate.

- [ ] **Step 3: Migrate emitted machine-readable identity**

```json
{"position":1,"source_id":"djing","track_id":42,"path":"Acid/Track.flac","role":"opener"}
```
Transitions may continue referencing paths for readability, but validation must resolve those paths to unique selected track identities.

- [ ] **Step 4: Run schema tests**

```bash
pytest tests/test_set_schema.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add schemas/dj-set.schema.json skills tests
git commit -m "feat: make set artifacts source aware"
```

### Task 4: Introduce V1B `tracks.tsv` availability contract

**Files:**
- Create/modify: `skills/electronic-dj-set-curator/references/source-contracts.md`
- Modify: `PROJECT_INSTRUCTIONS.md`, `SKILL.md`
- Create: `tests/fixtures/tracks.tsv`
- Test: `tests/validate_fixtures.py`

**Interfaces:**
- V1B precedence starts with `tracks.tsv`.

- [ ] **Step 1: Write failing contract assertions**

```python
required = ["tracks.tsv", "set_eligible", "source_id", "exact path"]
text = Path("PROJECT_INSTRUCTIONS.md").read_text() + Path("skills/electronic-dj-set-curator/SKILL.md").read_text()
assert all(token in text for token in required)
assert "djing-files.tsv: existence" not in text
```

- [ ] **Step 2: Run validator**

```bash
python tests/validate_fixtures.py
```
Expected: FAIL.

- [ ] **Step 3: Rewrite V1B source precedence exactly**

```text
1. tracks.tsv — current availability + source_id + set_eligible + exact path
2. dj-analysis.tsv — track/global/window technical facts
3. dj-sections.jsonl — structural facts
4. dj-analysis-run.json — audit/staleness signal
5. external context — classification/context only, never availability
```
Require membership plus `set_eligible=true` before a candidate enters optimization.

- [ ] **Step 4: Run validator**

```bash
python tests/validate_fixtures.py
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add PROJECT_INSTRUCTIONS.md skills tests/fixtures/tracks.tsv tests/validate_fixtures.py
git commit -m "feat: migrate curator availability to tracks export"
```

### Task 5: Enforce single-source M3U8 semantics and exact path validation

**Files:**
- Modify: skill emission/reference docs
- Test: `tests/test_playlist_emission.py`

**Interfaces:**
- M3U8 emits exact source-relative `path` only.
- Multi-source output requires an explicitly resolvable common library root; otherwise reject.

- [ ] **Step 1: Write failing mixed-source test**

```python
def test_default_m3u8_rejects_mixed_sources() -> None:
    with pytest.raises(AmbiguousLibraryRoot):
        emit_m3u8([track("djing", "A.flac"), track("archive", "B.flac")])
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_playlist_emission.py -q
```
Expected: FAIL.

- [ ] **Step 3: Encode emission rule**

```python
source_ids = {t.source_id for t in tracks}
if len(source_ids) != 1 and common_library_root is None:
    raise AmbiguousLibraryRoot(source_ids)
return "#EXTM3U\n" + "\n".join(t.path for t in tracks) + "\n"
```
No absolute path is written to M3U8 by default.

- [ ] **Step 4: Run test**

```bash
pytest tests/test_playlist_emission.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills tests/test_playlist_emission.py
git commit -m "feat: preserve exact set-copy playlist paths"
```

### Task 6: Remove first-party legacy inventory dependencies and lock V1B golden regression

**Files:**
- Modify: all first-party tests/docs/fixtures
- Delete: first-party fixture dependency on `djing-files.tsv`/`music-files.tsv`
- Test: `tests/test_golden_set.py`, `tests/validate_fixtures.py`

**Interfaces:**
- Legacy facets may still be generated by DJ Digger but are no longer required by the skill/project.

- [ ] **Step 1: Add failing repository scan for obsolete first-party references**

```python
for path in FIRST_PARTY_CONSUMER_FILES:
    text = path.read_text()
    assert "djing-files.tsv" not in text
    assert "music-files.tsv" not in text
```
Whitelist only migration/history documentation.

- [ ] **Step 2: Run migration checks**

```bash
python tests/validate_fixtures.py
pytest tests/test_golden_set.py tests/test_playlist_emission.py -q
```
Expected: FAIL while legacy references remain.

- [ ] **Step 3: Replace remaining fixtures/examples with `tracks.tsv`**

Preserve the same known Acid Rave core ordering and transition assertions while resolving candidates through source-aware rows.

- [ ] **Step 4: Run complete curator gate**

```bash
python tests/validate_fixtures.py
pytest -q
```
Expected: PASS with legacy compatibility facets absent from the test workspace.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: complete curator migration to tracks.tsv"
```
