# Refresh progress display design

## Goal

Give interactive users continuous visual feedback while `dj-digger refresh` runs, including
the current offset, total work, and an estimated completion time for track analysis. The
display must update in place and must not disturb the command's final JSON output.

## Scope

This first version instruments only `refresh`. It covers its scan, metadata, analysis, and
export phases. Standalone `scan`, `metadata`, `analyze`, and `export` commands keep their
current output behavior.

## Terminal behavior

The CLI creates one transient Rich progress display backed by `Console(stderr=True)`. Rich
owns a single live terminal area and rewrites it in place; progress updates never accumulate
as periodic lines.

The display contains:

- a global task showing the current refresh phase and an offset from 0 to 4;
- an analysis task showing completed tracks over selected tracks, percentage, processing
  speed, and estimated remaining time.

The analysis task is visible only while analysis is running. It begins at the number of
reused analyses and advances after each newly computed outcome has been persisted, whether
that outcome succeeded or failed. Consequently, completion reaches the selected-track total
without implying that every track succeeded.

The scan and metadata phases use an indeterminate spinner because the current implementations
do not expose incremental work while traversing a source or waiting for the batched ExifTool
call. Export is also represented as a phase rather than as per-file progress.

The progress display uses `transient=True`, so it is cleared before the existing final JSON
diagnostic is written to stdout. It is disabled when stderr is not an interactive terminal,
which preserves clean behavior for redirection, pipelines, cron jobs, and tests.

## Architecture

The domain and application layers do not import Rich. A small progress protocol represents
refresh phase changes and analysis counters. Its no-op implementation is the default, so
existing programmatic callers remain compatible.

The CLI owns a Rich-backed implementation and passes it to `WorkspaceApplication.refresh()`.
The application reports phase boundaries. `WorkspaceApplication.analyze()` forwards the same
reporter to `AnalysisPipeline`, which reports the selected total, reused count, and one
completion event immediately after every `persist_outcome()` call.

The reporter API carries semantic values rather than presentation instructions. Rich-specific
task identifiers, columns, refresh behavior, colors, and terminal detection remain confined
to the CLI adapter.

## Data flow

1. The `refresh` command opens the Rich reporter context on stderr.
2. `WorkspaceApplication.refresh()` starts and completes each of its four phases in order.
3. At analysis selection time, the pipeline reports `total=len(selected)` and
   `completed=len(reusable)`.
4. Each computed outcome is persisted atomically, then emits one completion event.
5. The pipeline closes the analysis task with the final counters.
6. The application completes the global task, including partial or failed results where
   execution can continue.
7. The reporter context clears the live display, and `_run()` writes the unchanged JSON
   diagnostic to stdout.

## Error handling

Progress reporting must not change command status or persistence semantics. A phase that
raises is marked failed before the exception follows the existing `_run()` error path. Early
refresh termination after a required scan failure closes the live display cleanly.

If Rich is disabled because stderr is not interactive, reporter calls remain valid no-ops.
Keyboard interruption and ordinary exceptions leave the reporter context, restoring the
terminal before Typer handles the process exit.

## Dependency

Add Rich as a direct, bounded runtime dependency. Although Typer may install Rich in some
environments, DJ Digger imports it directly and therefore declares it explicitly.

## Verification

Tests will verify:

- refresh phase ordering and the global 0/4 to 4/4 progression;
- analysis initialization with reused tracks already completed;
- one advancement after each persisted success or failure;
- zero-track analysis behavior;
- no progress rendering on non-interactive stderr;
- live output targets stderr while the final JSON remains on stdout;
- the progress context is closed on successful, partial, failed, and exceptional exits;
- existing refresh diagnostics and exit codes remain unchanged.

The normal Ruff, mypy, and Python test suite checks remain required.
