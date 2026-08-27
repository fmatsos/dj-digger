import re
import sqlite3

import pytest
from performance.benchmark_queries import (
    BENCHMARK_CASES_BY_NAME,
    compare_reconciliation_indexes,
)
from performance.fixtures import build_catalog
from performance.query_plans import explain

from dj_digger.catalog.database import Database


@pytest.fixture(scope="module")
def analyzed_database(tmp_path_factory: pytest.TempPathFactory) -> Database:
    path = build_catalog(
        tmp_path_factory.mktemp("query-plans") / "catalog.sqlite",
        tracks=2_500,
        analyses_per_track=3,
    )
    database = Database.open(path)
    _insert_reconciliation_rows(database, rows_per_source=2_500)
    database.execute("ANALYZE")
    yield database
    database.close()


@pytest.mark.parametrize(
    ("case_name", "table", "index_name"),
    [
        ("analysis_eligibility", "a", "idx_audio_analysis_success_lookup"),
        ("analysis_run_reconciliation", "audio_analysis", "idx_audio_analysis_run_status"),
        ("analysis_history", "audio_analysis", "idx_audio_analysis_track_history"),
        ("analysis_run_events", "track_events", "idx_track_events_analysis_run_type"),
        ("tracks_reconciliation", "tracks", "idx_tracks_present_reconciliation"),
        (
            "directories_reconciliation",
            "directories",
            "idx_directories_present_reconciliation",
        ),
        (
            "artifacts_reconciliation",
            "library_artifacts",
            "idx_library_artifacts_present_reconciliation",
        ),
    ],
)
def test_critical_query_searches_with_its_index(
    analyzed_database: Database,
    case_name: str,
    table: str,
    index_name: str,
) -> None:
    case = BENCHMARK_CASES_BY_NAME[case_name]

    details = explain(analyzed_database, case.sql or "", case.parameters)

    assert _has_index_search(details, table, index_name), details
    assert not _has_table_scan(details, table), details


@pytest.mark.parametrize("table", ["tracks", "directories", "library_artifacts"])
def test_source_path_unique_constraint_is_the_only_source_path_index(
    analyzed_database: Database, table: str
) -> None:
    source_path_indexes: list[tuple[int, str]] = []
    for _, name, unique, origin, _ in analyzed_database.execute(f"PRAGMA index_list({table})"):
        columns = tuple(
            str(row[2]) for row in analyzed_database.execute(f'PRAGMA index_info("{name}")')
        )
        if columns == ("source_id", "relative_path"):
            source_path_indexes.append((int(unique), str(origin)))

    assert source_path_indexes == [(1, "u")]


@pytest.mark.parametrize(
    ("table", "index_name"),
    [
        ("tracks", "idx_tracks_present_reconciliation"),
        ("directories", "idx_directories_present_reconciliation"),
        ("library_artifacts", "idx_library_artifacts_present_reconciliation"),
    ],
)
def test_reconciliation_keeps_only_the_measured_partial_shape(
    analyzed_database: Database, table: str, index_name: str
) -> None:
    reconciliation_indexes: list[tuple[str, tuple[str, ...], int]] = []
    for _, name, _, _, partial in analyzed_database.execute(f"PRAGMA index_list({table})"):
        columns = tuple(
            str(row[2]) for row in analyzed_database.execute(f'PRAGMA index_info("{name}")')
        )
        if "last_seen_scan_id" in columns:
            reconciliation_indexes.append((str(name), columns, int(partial)))

    assert reconciliation_indexes == [(index_name, ("source_id", "last_seen_scan_id"), 1)]


def test_reconciliation_benchmark_compares_both_index_shapes() -> None:
    measurements = compare_reconciliation_indexes(sizes=(100,), repetitions=1)

    assert len(measurements) == 8
    assert {measurement.shape for measurement in measurements} == {"full", "partial"}
    assert all(
        _has_index_search(
            [measurement.plan], measurement.table, f"idx_{measurement.table}_reconciliation"
        )
        for measurement in measurements
    )
    assert all(measurement.database_bytes > 0 for measurement in measurements)


def _has_index_search(details: list[str], table: str, index_name: str) -> bool:
    expected_table = table.casefold()
    expected_index = index_name.casefold()
    for detail in details:
        tokens = _plan_tokens(detail)
        if not tokens or tokens[0] != "search" or "index" not in tokens:
            continue
        index_token = tokens.index("index")
        if expected_table in tokens[1:index_token] and expected_index in tokens[index_token + 1 :]:
            return True
    return False


def _has_table_scan(details: list[str], table: str) -> bool:
    expected = table.casefold()
    for detail in details:
        tokens = _plan_tokens(detail)
        if len(tokens) < 2 or tokens[0] != "scan":
            continue
        using_token = tokens.index("using") if "using" in tokens else len(tokens)
        if expected in tokens[1:using_token]:
            return True
    return False


def _plan_tokens(detail: str) -> list[str]:
    return [token.casefold() for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", detail)]


def _insert_reconciliation_rows(database: Database, *, rows_per_source: int) -> None:
    timestamp = "2026-01-01T00:00:00+00:00"
    connection = database._connection
    with database.transaction():
        connection.execute(
            """
            INSERT INTO library_sources (
                source_id, root_path, set_eligible, analyze, enabled, created_at, updated_at
            ) VALUES ('other', '/benchmark/other', 1, 1, 1, ?, ?)
            """,
            (timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO scan_runs (
                id, source_id, started_at, finished_at, status, scanner_version
            ) VALUES (2, 'other', ?, ?, 'succeeded', 'benchmark-1.0')
            """,
            (timestamp, timestamp),
        )
        connection.executemany(
            """
            INSERT INTO tracks (
                source_id, relative_path, filename, extension, size_bytes, mtime_ns,
                presence_status, discovered_at, last_seen_at, created_scan_id, last_seen_scan_id
            ) VALUES ('other', ?, ?, '.flac', ?, ?, 'present', ?, ?, 2, 2)
            """,
            (
                (
                    f"Other/track-{row_id:09d}.flac",
                    f"track-{row_id:09d}.flac",
                    20_000_000 + row_id,
                    1_800_000_000_000_000_000 + row_id,
                    timestamp,
                    timestamp,
                )
                for row_id in range(1, rows_per_source + 1)
            ),
        )
        for table in ("directories", "library_artifacts"):
            _insert_presence_rows(
                connection,
                table=table,
                source_id="benchmark",
                scan_id=1,
                rows=rows_per_source,
                timestamp=timestamp,
            )
            _insert_presence_rows(
                connection,
                table=table,
                source_id="other",
                scan_id=2,
                rows=rows_per_source,
                timestamp=timestamp,
            )


def _insert_presence_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    source_id: str,
    scan_id: int,
    rows: int,
    timestamp: str,
) -> None:
    if table == "directories":
        connection.executemany(
            """
            INSERT INTO directories (
                source_id, relative_path, presence_status, discovered_at, last_seen_at,
                last_seen_scan_id
            ) VALUES (?, ?, 'present', ?, ?, ?)
            """,
            (
                (source_id, f"QueryPlanDirs/{row_id:09d}", timestamp, timestamp, scan_id)
                for row_id in range(1, rows + 1)
            ),
        )
        return
    connection.executemany(
        """
        INSERT INTO library_artifacts (
            source_id, relative_path, artifact_type, size_bytes, mtime_ns,
            presence_status, first_seen_at, last_seen_at, last_seen_scan_id
        ) VALUES (?, ?, 'playlist', 100, 100, 'present', ?, ?, ?)
        """,
        (
            (source_id, f"QueryPlanArtifacts/{row_id:09d}.m3u8", timestamp, timestamp, scan_id)
            for row_id in range(1, rows + 1)
        ),
    )
