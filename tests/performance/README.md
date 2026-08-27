# Catalog performance harness

This directory provides deterministic SQLite catalogs and named V6/V7 query cases for local
measurement. CI tests assert cardinality, semantics, and query plans; elapsed-time thresholds stay
local because shared runners do not provide stable timing evidence.

`fixtures.SCENARIOS` covers 10k/1, 50k/5, 100k/5, and 250k/10 track/history shapes. The builder
migrates a fresh catalog, uses bounded `executemany()` batches, and gives every track deterministic
paths, input facts, metadata, alternating analysis history ending in success, and two lifecycle
events. Pass a new database path: the builder refuses to overwrite an existing catalog.

`benchmark_queries.py` names the existing V6 operations and the V7 `library_tracks` listing and
keyset-pagination operations. The `database_open` case has no SQL because the measured operation is
opening and configuring the connection itself. Run mutating reconciliation cases inside a
transaction that is rolled back so later measurements see the same dataset.

`query_plans.explain()` returns the stable detail column from `EXPLAIN QUERY PLAN`.
`has_full_scan()` deliberately matches table scans by normalized table token instead of comparing
SQLite's complete, version-dependent wording.

Run the focused semantic check with Python 3.12:

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uv run --python 3.12 --with pytest python -m pytest tests/test_performance_fixtures.py -q
```

Record machine details, SQLite version, scenario, warm-up policy, repetitions, and median timings
alongside any local index experiment. Do not promote local elapsed-time numbers to CI assertions.

## Reconciliation index decision (2026-08-27)

The retained V7 shape is the partial index on `(source_id, last_seen_scan_id) WHERE
presence_status = 'present'` for `tracks`, `directories`, and `library_artifacts`. The discarded
candidate was the full `(source_id, presence_status, last_seen_scan_id)` index. Fresh and V6-to-V7
SQL contain only the partial form.

Measurements ran on Linux 7.0.0-30-generic x86_64 with Python 3.12.13 and SQLite 3.53.1. The
dedicated fixture creates 10k, 100k, or 250k rows in each reconciliation table, without metadata,
analysis history, or events. Each table has one source, 90% present rows, 10% missing rows, and 1%
of all rows both present and stale. It keeps the existing unique `(source_id, relative_path)`
constraint, creates exactly one candidate reconciliation index, runs `ANALYZE`, performs one
warm-up, then reports the median of seven wall-clock repetitions. Selects fetch every result;
updates execute inside a transaction rolled back after every repetition. Database size is
`page_count * page_size` for all three tables and their indexes.

Run the comparison with:

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uv run --python 3.12 python tests/performance/benchmark_queries.py
```

The observed medians in milliseconds were:

| Rows per table | Shape | Track select | Track update | Directory update | Artifact update | Database MiB |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 10,000 | full | 0.437 | 1.116 | 1.090 | 1.247 | 3.10 |
| 10,000 | partial | 0.389 | 1.019 | 1.011 | 0.988 | 2.82 |
| 100,000 | full | 4.889 | 11.068 | 10.588 | 10.472 | 31.45 |
| 100,000 | partial | 4.473 | 10.545 | 11.601 | 11.654 | 28.59 |
| 250,000 | full | 13.913 | 34.898 | 35.913 | 38.378 | 78.93 |
| 250,000 | partial | 13.718 | 29.953 | 29.632 | 26.048 | 71.79 |

Both candidates produced `SEARCH ... USING INDEX` plans after `ANALYZE`; neither could turn
`last_seen_scan_id != ?` into a selective range. The full form used the equality prefix
`(source_id, presence_status)`, while the partial form used `source_id` and encoded the present-row
predicate in the index itself. At 250k rows the partial form reduced aggregate database size by
9.0%, track update time by 14.2%, directory update time by 17.5%, and artifact update time by 32.1%;
track select time was effectively tied (1.4% lower). Two 100k update medians favored the full form,
which is treated as local timing noise rather than a different query-plan result. The smaller
partial form wins on storage and high-cardinality scaling while preserving indexed searches, so it
is the V7 choice. Timing values are evidence for this local decision, not CI thresholds.

## WAL concurrency qualification (2026-08-27)

`tests/test_sqlite_concurrency.py` qualifies WAL behavior with file-backed catalogs and independent
`DatabaseFactory.open()` connections. Every worker opens, queries, and closes its own connection in
the same thread; no `sqlite3.Connection` crosses a thread boundary. Synchronization uses bounded
`threading.Event` waits rather than elapsed-time performance assertions.

The qualification covers a reader observing the committed pre-write snapshot while another
connection holds an uncommitted transaction, eight readers each performing five open/query/close
cycles while a 500-row batch remains uncommitted, and two competing-writer cases. A waiting writer
succeeds when the first writer is released within the configured 5,000 ms timeout. The deliberately
overlong-lock case sets `PRAGMA busy_timeout = 100` only on its competing connection, confirms the
expected `database is locked` error within the test's three-second synchronization bound, then
proves a fresh write succeeds after release. Thread exceptions are collected, all release events
are signalled in cleanup, and every worker is joined before assertions about final database state.

Run the qualification with Python 3.12:

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache UV_TOOL_DIR=/tmp/dj-digger-uv-tools \
  uv run --python 3.12 --with pytest python -m pytest tests/test_sqlite_concurrency.py -q
```

The focused qualification passed all four cases on Linux 7.0.0-30-generic x86_64 with Python
3.12.13 and SQLite 3.53.1. These are synchronization and correctness results, not throughput
measurements; the suite intentionally records no elapsed-time acceptance threshold.

## Catalog V6/V7 release requalification (2026-08-27)

The release comparison used the existing `fixtures.build_catalog()` cardinalities and named
`V6_BENCHMARK_CASES`/`V7_BENCHMARK_CASES`. For each scenario, a deterministic catalog was reduced
to the V6 schema by removing only the seven V7 indexes, `current_track_analysis`, and
`library_tracks`, setting `user_version = 6`, then running `VACUUM` and `ANALYZE`. A byte-for-byte
copy of that V6 file was upgraded through `Database.migrate()` and analyzed. Thus both sides have
identical canonical rows; V7 additionally has its indexes, backfilled projection, and view.

The versioned harness does not currently orchestrate this complete before/after run. A temporary
driver in `/tmp` imported its fixtures and cases and added only measurement orchestration. For the
two V7 read cases, the V6 side used the SQL-equivalent latest-success CTE and the same selected
columns, ordering, and limit; the V7 side queried `library_tracks`. This is an acceptance driver,
not a claimed checked-in harness feature.

Measurements ran on Linux 7.0.0-30-generic x86_64 (14 logical CPUs) with Python 3.12.13 and SQLite
3.53.1. Each query received one warm-up followed by three repetitions; the tables report the
median wall time in milliseconds. “Warm” keeps one connection. “Cold connection” opens a new
SQLite connection for each repetition, resetting its page cache but **not** purging the host OS
cache. Selects fetch every row, mutations run inside a rolled-back transaction, and `database_open`
uses `Database.open()`/`close()`. These local timings are evidence, not CI thresholds.

The measured cardinalities and logical database sizes (`page_count * page_size`) were:

| Tracks | Analyses/track | Analyses | Events | Directories | Artifacts | V6 MiB | V7 MiB | V7 current rows |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 1 | 10,000 | 20,000 | 10 | 500 | 7.63 | 11.14 | 10,000 |
| 50,000 | 5 | 250,000 | 100,000 | 50 | 2,500 | 75.48 | 110.21 | 50,000 |
| 100,000 | 5 | 500,000 | 200,000 | 100 | 5,000 | 150.96 | 221.09 | 100,000 |
| 250,000 | 10 | 2,500,000 | 500,000 | 250 | 12,500 | 610.59 | 880.32 | 250,000 |

Columns below are V6 warm, V6 cold-connection, V7 warm, and V7 cold-connection medians.

| 10k tracks / 10k analyses | V6 W | V6 C | V7 W | V7 C |
| --- | ---: | ---: | ---: | ---: |
| database_open | 0.234 | 0.229 | 0.343 | 0.334 |
| status_counts | 1.666 | 2.961 | 2.017 | 3.135 |
| scan_reconciliation_select | 3.142 | 4.224 | 2.190 | 3.677 |
| scan_reconciliation_update | 6.899 | 8.233 | 13.279 | 13.238 |
| metadata_eligibility | 7.632 | 8.548 | 9.525 | 10.071 |
| analysis_eligibility | 13.743 | 16.863 | 6.239 | 4.978 |
| analysis_history | 0.392 | 2.039 | 0.010 | 0.264 |
| track_export | 40.800 | 39.325 | 39.122 | 32.697 |
| analysis_export_selection | 41.150 | 45.294 | 45.482 | 51.588 |
| latest_analysis_run | 0.007 | 0.200 | 0.007 | 0.241 |
| library_listing | 31.810 | 36.437 | 6.194 | 6.658 |
| pagination | 0.151 | 0.511 | 0.095 | 0.543 |

| 50k tracks / 250k analyses | V6 W | V6 C | V7 W | V7 C |
| --- | ---: | ---: | ---: | ---: |
| database_open | 0.242 | 0.214 | 0.389 | 0.348 |
| status_counts | 12.921 | 13.351 | 13.576 | 13.668 |
| scan_reconciliation_select | 21.620 | 25.638 | 16.313 | 19.150 |
| scan_reconciliation_update | 43.257 | 43.235 | 97.280 | 94.689 |
| metadata_eligibility | 46.749 | 45.357 | 51.961 | 51.450 |
| analysis_eligibility | 205.663 | 211.664 | 55.973 | 61.835 |
| analysis_history | 20.730 | 20.524 | 0.013 | 0.329 |
| track_export | 222.383 | 203.884 | 240.536 | 227.784 |
| analysis_export_selection | 724.705 | 757.243 | 583.713 | 603.370 |
| latest_analysis_run | 0.008 | 0.193 | 0.007 | 0.269 |
| library_listing | 240.388 | 240.797 | 5.537 | 6.441 |
| pagination | 0.151 | 0.551 | 0.080 | 0.446 |

| 100k tracks / 500k analyses (release gate) | V6 W | V6 C | V7 W | V7 C |
| --- | ---: | ---: | ---: | ---: |
| database_open | 0.237 | 0.233 | 0.515 | 0.448 |
| status_counts | 36.491 | 33.450 | 32.408 | 32.014 |
| scan_reconciliation_select | 44.073 | 44.612 | 37.186 | 37.227 |
| scan_reconciliation_update | 95.408 | 99.605 | 188.815 | 185.151 |
| metadata_eligibility | 101.949 | 113.430 | 103.281 | 99.670 |
| analysis_eligibility | 474.701 | 447.783 | 116.618 | 112.594 |
| analysis_history | 39.950 | 41.774 | 0.011 | 0.266 |
| track_export | 412.873 | 455.339 | 422.983 | 411.429 |
| analysis_export_selection | 1,480.283 | 1,446.447 | 1,211.042 | 1,165.520 |
| latest_analysis_run | 0.013 | 0.259 | 0.009 | 0.319 |
| library_listing | 483.595 | 485.567 | 5.581 | 6.125 |
| pagination | 471.882 | 480.214 | 5.148 | 6.336 |

| 250k tracks / 2.5M analyses (qualification) | V6 W | V6 C | V7 W | V7 C |
| --- | ---: | ---: | ---: | ---: |
| database_open | 0.315 | 0.281 | 0.550 | 0.482 |
| status_counts | 80.820 | 84.064 | 89.269 | 82.574 |
| scan_reconciliation_select | 118.495 | 123.589 | 100.821 | 96.309 |
| scan_reconciliation_update | 247.018 | 246.827 | 533.315 | 518.709 |
| metadata_eligibility | 273.882 | 273.099 | 309.006 | 287.002 |
| analysis_eligibility | 1,870.013 | 1,969.767 | 387.196 | 369.752 |
| analysis_history | 200.876 | 194.325 | 0.016 | 0.255 |
| track_export | 1,101.252 | 1,106.241 | 1,066.085 | 1,133.121 |
| analysis_export_selection | 7,147.387 | 7,001.150 | 5,018.050 | 5,043.825 |
| latest_analysis_run | 0.010 | 0.284 | 0.009 | 0.320 |
| library_listing | 1,628.592 | 1,579.813 | 5.842 | 6.771 |
| pagination | 1,620.747 | 1,597.110 | 6.195 | 5.341 |

At the 100k release gate, normalized `EXPLAIN QUERY PLAN` details were:

| Case | V6 | V7 |
| --- | --- | --- |
| status_counts | `SCAN tracks; USE TEMP B-TREE FOR GROUP BY` | same |
| scan_reconciliation_select | `SCAN tracks` | `SEARCH tracks USING COVERING INDEX idx_tracks_present_reconciliation (source_id=?)` |
| scan_reconciliation_update | `SCAN tracks` | `SEARCH tracks USING INDEX idx_tracks_present_reconciliation (source_id=?)` |
| metadata_eligibility | `SCAN t; SEARCH m USING INTEGER PRIMARY KEY (rowid=?) LEFT-JOIN` | same |
| analysis_eligibility | track/source scans; automatic partial covering search of `a` | track/source scans; `SEARCH a USING COVERING INDEX idx_audio_analysis_success_lookup (...) LEFT-JOIN` |
| analysis_history | `SCAN audio_analysis` | `SEARCH audio_analysis USING INDEX idx_audio_analysis_track_history (track_id=?)` |
| track_export | ordered track scan plus primary-key metadata lookups | same |
| analysis_export_selection | history scan plus temporary sort | `SCAN a USING INDEX idx_audio_analysis_track_history`; no temporary history sort |
| latest_analysis_run | `SCAN analysis_runs` | same |
| library_listing | materialize latest-success history with `SCAN audio_analysis` and temporary group | ordered track scan plus primary-key joins to metadata, technical data, and `current` |
| pagination | materialize latest-success history, then `SEARCH t USING INTEGER PRIMARY KEY (rowid>?)` | `SEARCH t USING INTEGER PRIMARY KEY (rowid>?)` plus primary-key joins |

The query-plan regression gate separately checks analysis-run reconciliation and event lookup, and
passed without critical historical-analysis or event full scans. The timing evidence has one clear
trade-off: reconciliation **updates** are about twice as slow in V7 when all fixture tracks match
the predicate, because maintaining the partial index costs more than the V6 table scan. Selects
improve and the dedicated 1%-stale experiment above favored the partial index at high cardinality.
This all-match result is retained as a release concern; it is not hidden by the faster indexed
read cases.
