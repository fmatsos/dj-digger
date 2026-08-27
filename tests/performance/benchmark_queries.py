"""Named SQL operations and local reconciliation index benchmarks."""

import platform
import sqlite3
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkCase:
    """One named operation whose timing and plan can be inspected locally."""

    name: str
    sql: str | None
    parameters: tuple[object, ...] = ()
    catalog_version: int = 6
    mutates: bool = False


V6_BENCHMARK_CASES = (
    BenchmarkCase("database_open", None),
    BenchmarkCase(
        "status_counts",
        """
        SELECT presence_status, COUNT(*)
        FROM tracks
        WHERE source_id = ?
        GROUP BY presence_status
        """,
        ("benchmark",),
    ),
    BenchmarkCase(
        "scan_reconciliation_select",
        """
        SELECT id FROM tracks
        WHERE source_id = ? AND presence_status = 'present' AND last_seen_scan_id != ?
        """,
        ("benchmark", 2),
    ),
    BenchmarkCase(
        "scan_reconciliation_update",
        """
        UPDATE tracks SET presence_status = 'missing', missing_since = ?
        WHERE source_id = ? AND presence_status = 'present' AND last_seen_scan_id != ?
        """,
        ("2026-01-02T00:00:00+00:00", "benchmark", 2),
        mutates=True,
    ),
    BenchmarkCase(
        "metadata_eligibility",
        """
        SELECT t.id, t.source_id, t.relative_path, t.filename, t.extension,
               t.size_bytes, t.mtime_ns, t.presence_status
        FROM tracks t
        LEFT JOIN embedded_metadata m ON m.track_id = t.id
        WHERE t.presence_status = 'present' AND (
            m.track_id IS NULL OR m.input_size_bytes IS NULL OR m.input_mtime_ns IS NULL OR
            m.input_size_bytes != t.size_bytes OR m.input_mtime_ns != t.mtime_ns OR
            m.extractor_version != ? OR m.normalization_version != ?
        )
        ORDER BY t.id
        """,
        ("benchmark-1.0", "1"),
    ),
    BenchmarkCase(
        "analysis_eligibility",
        """
        SELECT t.id, t.source_id, t.relative_path, t.filename, t.extension,
               t.size_bytes, t.mtime_ns, t.presence_status
        FROM tracks t
        JOIN library_sources s ON s.source_id = t.source_id
        LEFT JOIN audio_analysis a ON a.track_id = t.id
          AND a.input_size_bytes = t.size_bytes
          AND a.input_mtime_ns = t.mtime_ns
          AND a.analysis_schema_version = ?
          AND a.analyzer_version = ?
          AND a.config_hash = ?
          AND a.analysis_status = 'succeeded'
        WHERE t.presence_status = 'present' AND s.enabled = 1 AND s.analyze = 1
          AND a.id IS NULL
        ORDER BY t.source_id, t.relative_path, t.id
        """,
        (2, "benchmark-1.0", "b" * 64),
    ),
    BenchmarkCase(
        "analysis_history",
        """
        SELECT id, analysis_status, input_size_bytes, input_mtime_ns,
               analysis_schema_version, analyzer_version, config_hash
        FROM audio_analysis
        WHERE track_id = ?
        ORDER BY id DESC
        """,
        (1,),
    ),
    BenchmarkCase(
        "track_export",
        """
        SELECT t.id, t.source_id, t.relative_path, t.filename, t.extension,
               t.size_bytes, t.mtime_ns, s.set_eligible,
               e.title, e.artist, e.album_artist, e.album, e.track_number,
               e.disc_number, e.genre, e.date, e.year, e.composer, e.comment,
               e.tag_bpm, e.tag_initial_key, e.grouping,
               a.duration_seconds, a.sample_rate, a.channels, a.codec,
               a.container, a.bitrate, a.lossless
        FROM tracks t
        JOIN library_sources s ON s.source_id = t.source_id
        LEFT JOIN embedded_metadata e ON e.track_id = t.id
        LEFT JOIN technical_audio_metadata a ON a.track_id = t.id
        WHERE t.presence_status = 'present'
        ORDER BY t.source_id, t.relative_path, t.id
        """,
    ),
    BenchmarkCase(
        "analysis_export_selection",
        """
        WITH current_attempt AS (
            SELECT a.*,
                   ROW_NUMBER() OVER (PARTITION BY a.track_id ORDER BY a.id DESC) AS rank
            FROM audio_analysis a
        )
        SELECT t.source_id, t.id, t.relative_path, t.size_bytes, t.mtime_ns,
               a.analysis_schema_version, a.analyzer_version, a.config_hash,
               a.analysis_status, a.analysis_confidence, a.payload_json, a.id
        FROM current_attempt a
        JOIN tracks t ON t.id = a.track_id
        WHERE a.rank = 1 AND t.presence_status = 'present'
        ORDER BY t.source_id, t.relative_path, t.id
        """,
    ),
    BenchmarkCase(
        "latest_analysis_run",
        """
        SELECT id, started_at, finished_at, status, eligible, analyzed, reused, failed,
               analysis_schema_version, analyzer_version, config_hash
        FROM analysis_runs
        ORDER BY id DESC
        LIMIT 1
        """,
    ),
)

V7_BENCHMARK_CASES = (
    BenchmarkCase(
        "library_listing",
        """
        SELECT * FROM library_tracks
        ORDER BY source_id, relative_path, track_id
        LIMIT ?
        """,
        (1_000,),
        catalog_version=7,
    ),
    BenchmarkCase(
        "pagination",
        """
        SELECT * FROM library_tracks
        WHERE track_id > ?
        ORDER BY track_id
        LIMIT ?
        """,
        (50_000, 1_000),
        catalog_version=7,
    ),
)

QUERY_PLAN_CASES = (
    BenchmarkCase(
        "analysis_run_reconciliation",
        """
        SELECT COALESCE(SUM(analysis_status = 'succeeded'), 0),
               COALESCE(SUM(analysis_status = 'failed'), 0)
        FROM audio_analysis
        WHERE analysis_run_id = ?
        """,
        (2,),
        catalog_version=7,
    ),
    BenchmarkCase(
        "analysis_run_events",
        """
        SELECT track_id, payload_json
        FROM track_events
        WHERE analysis_run_id = ? AND event_type = ?
        ORDER BY track_id, id
        """,
        (3, "analysis_completed"),
        catalog_version=7,
    ),
    BenchmarkCase(
        "tracks_reconciliation",
        """
        SELECT id FROM tracks
        WHERE source_id = ? AND presence_status = 'present' AND last_seen_scan_id != ?
        """,
        ("benchmark", 2),
        catalog_version=7,
    ),
    BenchmarkCase(
        "directories_reconciliation",
        """
        UPDATE directories SET presence_status = 'missing', missing_since = ?
        WHERE source_id = ? AND presence_status = 'present' AND last_seen_scan_id != ?
        """,
        ("2026-01-02T00:00:00+00:00", "benchmark", 2),
        catalog_version=7,
        mutates=True,
    ),
    BenchmarkCase(
        "artifacts_reconciliation",
        """
        UPDATE library_artifacts SET presence_status = 'missing', missing_since = ?
        WHERE source_id = ? AND presence_status = 'present' AND last_seen_scan_id != ?
        """,
        ("2026-01-02T00:00:00+00:00", "benchmark", 2),
        catalog_version=7,
        mutates=True,
    ),
)

ALL_BENCHMARK_CASES = V6_BENCHMARK_CASES + V7_BENCHMARK_CASES
BENCHMARK_CASES_BY_NAME = {case.name: case for case in ALL_BENCHMARK_CASES + QUERY_PLAN_CASES}

RECONCILIATION_SIZES = (10_000, 100_000, 250_000)
RECONCILIATION_TABLES = ("tracks", "directories", "library_artifacts")
RECONCILIATION_SHAPES = ("full", "partial")


@dataclass(frozen=True)
class ReconciliationMeasurement:
    """One median local result for an index shape and reconciliation query."""

    rows: int
    shape: str
    table: str
    operation: str
    median_ms: float
    plan: str
    database_bytes: int


def compare_reconciliation_indexes(
    *,
    sizes: tuple[int, ...] = RECONCILIATION_SIZES,
    repetitions: int = 7,
) -> list[ReconciliationMeasurement]:
    """Measure full and partial reconciliation indexes on lightweight fixtures."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")

    measurements: list[ReconciliationMeasurement] = []
    with tempfile.TemporaryDirectory(prefix="dj-digger-reconciliation-") as directory:
        root = Path(directory)
        for rows in sizes:
            if rows < 1:
                raise ValueError("sizes must contain only positive row counts")
            for shape in RECONCILIATION_SHAPES:
                path = root / f"reconciliation-{rows}-{shape}.sqlite"
                connection = _build_reconciliation_catalog(path, rows=rows, shape=shape)
                try:
                    database_bytes = _database_bytes(connection)
                    for table in RECONCILIATION_TABLES:
                        operations = ("select", "update") if table == "tracks" else ("update",)
                        for operation in operations:
                            sql, parameters = _reconciliation_query(table, operation)
                            plan = " | ".join(
                                str(row[3])
                                for row in connection.execute(
                                    f"EXPLAIN QUERY PLAN {sql}", parameters
                                )
                            )
                            median_ms = _median_query_ms(
                                connection,
                                sql,
                                parameters,
                                mutates=operation == "update",
                                repetitions=repetitions,
                            )
                            measurements.append(
                                ReconciliationMeasurement(
                                    rows=rows,
                                    shape=shape,
                                    table=table,
                                    operation=operation,
                                    median_ms=median_ms,
                                    plan=plan,
                                    database_bytes=database_bytes,
                                )
                            )
                finally:
                    connection.close()
    return measurements


def _build_reconciliation_catalog(path: Path, *, rows: int, shape: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    for table in RECONCILIATION_TABLES:
        connection.execute(
            f"""
            CREATE TABLE {table} (
                id INTEGER PRIMARY KEY,
                source_id TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                presence_status TEXT NOT NULL,
                missing_since TEXT NULL,
                last_seen_scan_id INTEGER NOT NULL,
                UNIQUE(source_id, relative_path)
            )
            """
        )
        connection.executemany(
            f"""
            INSERT INTO {table} (
                id, source_id, relative_path, presence_status, missing_since, last_seen_scan_id
            ) VALUES (?, 'benchmark', ?, ?, NULL, ?)
            """,
            (
                (
                    row_id,
                    f"item-{row_id:09d}",
                    "missing" if row_id % 10 == 0 else "present",
                    1 if row_id % 100 == 1 else 2,
                )
                for row_id in range(1, rows + 1)
            ),
        )
        index_name = f"idx_{table}_reconciliation"
        if shape == "full":
            connection.execute(
                f"CREATE INDEX {index_name} "
                f"ON {table} (source_id, presence_status, last_seen_scan_id)"
            )
        elif shape == "partial":
            connection.execute(
                f"CREATE INDEX {index_name} ON {table} (source_id, last_seen_scan_id) "
                "WHERE presence_status = 'present'"
            )
        else:
            raise ValueError(f"unsupported reconciliation index shape: {shape}")
    connection.execute("ANALYZE")
    connection.commit()
    return connection


def _reconciliation_query(table: str, operation: str) -> tuple[str, tuple[object, ...]]:
    predicate = "source_id = ? AND presence_status = 'present' AND last_seen_scan_id != ?"
    if operation == "select":
        return f"SELECT id FROM {table} WHERE {predicate}", ("benchmark", 2)
    if operation == "update":
        return (
            f"UPDATE {table} SET presence_status = 'missing', missing_since = ? WHERE {predicate}",
            ("2026-01-02T00:00:00+00:00", "benchmark", 2),
        )
    raise ValueError(f"unsupported reconciliation operation: {operation}")


def _median_query_ms(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[object, ...],
    *,
    mutates: bool,
    repetitions: int,
) -> float:
    _run_rolled_back(connection, sql, parameters, mutates=mutates)
    elapsed: list[float] = []
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        _run_rolled_back(connection, sql, parameters, mutates=mutates)
        elapsed.append((time.perf_counter_ns() - started) / 1_000_000)
    return statistics.median(elapsed)


def _run_rolled_back(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[object, ...],
    *,
    mutates: bool,
) -> None:
    connection.execute("BEGIN")
    try:
        cursor = connection.execute(sql, parameters)
        if not mutates:
            cursor.fetchall()
    finally:
        connection.rollback()


def _database_bytes(connection: sqlite3.Connection) -> int:
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    return page_count * page_size


def _print_reconciliation_report() -> None:
    print(
        f"machine={platform.platform()} processor={platform.processor() or 'unknown'} "
        f"python={platform.python_version()} sqlite={sqlite3.sqlite_version}"
    )
    print("method=1 warm-up, 7 repetitions, median wall time, each mutation rolled back")
    for result in compare_reconciliation_indexes():
        print(
            f"rows={result.rows} shape={result.shape} table={result.table} "
            f"operation={result.operation} median_ms={result.median_ms:.3f} "
            f"database_mib={result.database_bytes / 1024 / 1024:.2f} plan={result.plan}"
        )


if __name__ == "__main__":
    _print_reconciliation_report()
