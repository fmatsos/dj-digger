# Refresh Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-place Rich progress display to `refresh`, with global phase progress and per-track analysis offset, speed, and ETA.

**Architecture:** Define an optional semantic progress protocol in a focused module and pass it through `WorkspaceApplication.refresh()` to `AnalysisPipeline`. Keep Rich confined to a CLI adapter using a transient stderr console; application code and tests use a no-op or recording reporter.

**Tech Stack:** Python 3.12, Typer, Rich, pytest, Ruff, mypy

---

### Task 1: Semantic progress contract

**Files:**
- Create: `src/dj_digger/progress.py`
- Test: `tests/test_progress.py`

- [ ] **Step 1: Write failing tests for the no-op reporter**

```python
from dj_digger.progress import NullProgressReporter


def test_null_progress_reporter_accepts_the_complete_lifecycle() -> None:
    reporter = NullProgressReporter()
    reporter.phase_started("scan", 1, 4)
    reporter.analysis_started(total=3, completed=1)
    reporter.analysis_advanced()
    reporter.analysis_finished()
    reporter.phase_finished("scan", 1, 4)
```

- [ ] **Step 2: Run the focused test and verify the import fails**

Run: `pytest tests/test_progress.py -q`

Expected: FAIL because `dj_digger.progress` does not exist.

- [ ] **Step 3: Add the typed protocol and no-op implementation**

```python
from typing import Protocol


class ProgressReporter(Protocol):
    def phase_started(self, name: str, completed: int, total: int) -> None: ...
    def phase_finished(self, name: str, completed: int, total: int) -> None: ...
    def analysis_started(self, *, total: int, completed: int) -> None: ...
    def analysis_advanced(self) -> None: ...
    def analysis_finished(self) -> None: ...


class NullProgressReporter:
    def phase_started(self, name: str, completed: int, total: int) -> None: pass
    def phase_finished(self, name: str, completed: int, total: int) -> None: pass
    def analysis_started(self, *, total: int, completed: int) -> None: pass
    def analysis_advanced(self) -> None: pass
    def analysis_finished(self) -> None: pass
```

- [ ] **Step 4: Run the focused test**

Run: `pytest tests/test_progress.py -q`

Expected: PASS.

### Task 2: Pipeline completion events

**Files:**
- Modify: `src/dj_digger/analysis/pipeline.py:41-169`
- Modify: `tests/test_analysis_pipeline.py`

- [ ] **Step 1: Add a recording reporter test covering reuse, success, and failure**

Create a reporter that appends calls, seed one reusable track, leave one successful track and
one failing track pending, then assert:

```python
assert reporter.events[0] == ("analysis_started", 3, 1)
assert reporter.events.count(("analysis_advanced",)) == 2
assert reporter.events[-1] == ("analysis_finished",)
```

Also add an empty selection test asserting `analysis_started(total=0, completed=0)` followed by
`analysis_finished()` and no advancement.

- [ ] **Step 2: Run the new pipeline tests and verify they fail**

Run: `pytest tests/test_analysis_pipeline.py -q`

Expected: FAIL because `AnalysisPipeline` does not accept a reporter.

- [ ] **Step 3: Inject the reporter and emit lifecycle events**

Extend the constructor with `progress: ProgressReporter | None = None`, store
`progress or NullProgressReporter()`, call `analysis_started()` after reusable and pending
selection, call `analysis_advanced()` immediately after each successful
`persist_outcome()`, and close the lifecycle with `analysis_finished()` in a `finally` block
around extraction and run finalization.

- [ ] **Step 4: Run pipeline tests**

Run: `pytest tests/test_analysis_pipeline.py -q`

Expected: all pipeline tests PASS, including persistence-error behavior.

### Task 3: Refresh phase orchestration

**Files:**
- Modify: `src/dj_digger/application.py:37-190`
- Modify: `tests/test_application_contracts.py`

- [ ] **Step 1: Add tests for phase ordering and early failure**

Use a recording reporter and assert a successful refresh emits paired phase events in this
order:

```python
[
    ("started", "scan", 0, 4), ("finished", "scan", 1, 4),
    ("started", "metadata", 1, 4), ("finished", "metadata", 2, 4),
    ("started", "analysis", 2, 4), ("finished", "analysis", 3, 4),
    ("started", "exports", 3, 4), ("finished", "exports", 4, 4),
]
```

Add a required-scan-failure assertion that only the scan pair is emitted and publication
remains disabled.

- [ ] **Step 2: Run focused application tests and verify failure**

Run: `pytest tests/test_application_contracts.py -q`

Expected: FAIL because `refresh()` does not accept a reporter.

- [ ] **Step 3: Add reporter plumbing**

Change `refresh(progress: ProgressReporter | None = None)` to use a no-op default, wrap each
phase in semantic start/finish calls, and pass the reporter through `analyze(progress=...)` to
`AnalysisPipeline(..., progress=...)`. Preserve the existing result dictionaries, statuses,
early scan return, and export exception handling byte-for-byte where possible.

- [ ] **Step 4: Run focused application tests**

Run: `pytest tests/test_application_contracts.py -q`

Expected: PASS.

### Task 4: Rich live terminal adapter

**Files:**
- Create: `src/dj_digger/rich_progress.py`
- Modify: `src/dj_digger/cli.py:1-150`
- Modify: `tests/test_cli_refresh.py`
- Modify: `pyproject.toml:10-16`
- Modify: `uv.lock`

- [ ] **Step 1: Add failing adapter and CLI tests**

Test the adapter with a Rich `Console` backed by `io.StringIO`, `force_terminal=True`, and a
deterministic clock. Assert rendered output contains `2/4`, `1/3`, and `ETA`, while repeated
advances rewrite a live display rather than emitting application log lines. Add a CLI test
that monkeypatches the reporter factory and asserts `refresh(progress=reporter)` is called.
Add a non-interactive test with `force_terminal=False` asserting the buffer stays empty.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/test_progress.py tests/test_cli_refresh.py -q`

Expected: FAIL because the Rich adapter and CLI factory do not exist.

- [ ] **Step 3: Declare Rich directly**

Add `"rich>=14,<16"` to project dependencies and refresh the existing lock file with:

Run: `uv lock`

Expected: `dj-digger` directly references Rich and the lock remains consistent.

- [ ] **Step 4: Implement the Rich adapter**

Build one `Progress` instance with `transient=True`, `console=Console(stderr=True)`, and
columns for description, bar/spinner, `{task.completed:.0f}/{task.total:.0f}`, percentage,
speed, and `TimeRemainingColumn`. The global task has total 4. The analysis task is added and
removed for the analysis lifecycle. Set `disable=not console.is_terminal` and keep
`redirect_stdout=False`, `redirect_stderr=False` so the existing JSON/logging streams remain
under application control.

- [ ] **Step 5: Connect only the refresh CLI command**

Enter the reporter context inside `refresh`, pass it to `service.refresh(progress=reporter)`,
and leave every standalone command unchanged. Ensure the reporter context exits before
`_run()` prints the diagnostic by having the action return the result after its inner context.

- [ ] **Step 6: Run focused CLI tests**

Run: `pytest tests/test_progress.py tests/test_cli_refresh.py tests/test_cli_status_codes.py -q`

Expected: PASS; redirected invocation still exposes only the existing JSON diagnostic.

### Task 5: Documentation and full verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document interactive refresh progress**

Add a concise note near the refresh workflow: interactive terminals show a transient Rich
display with phase offset and analysis ETA; redirected/non-interactive execution keeps clean
JSON output.

- [ ] **Step 2: Run formatting and static checks**

Run: `ruff check src tests`

Expected: PASS.

Run: `mypy src`

Expected: PASS on all source files.

- [ ] **Step 3: Run the complete test suite**

Run: `pytest -q`

Expected: all tests PASS, apart from the repository's documented optional skip.

- [ ] **Step 4: Check the final diff**

Run: `git diff --check`

Expected: no output.

Review `git status --short` and ensure pre-existing local paths remain unstaged, especially
`references/copy-set.sh`, `config/local.toml`, `sets/`, `workspace/`, and all
`docs/superpowers/specs/*` and `docs/superpowers/plans/*` files.
