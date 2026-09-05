"""Deterministic, bulk-loaded SQLite catalogs for local benchmarks."""

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from dj_digger.catalog.database import Database

SCENARIOS = ((10_000, 1), (50_000, 5), (100_000, 5), (250_000, 10))

SOURCE_ID = "benchmark"
SCANNER_VERSION = "benchmark-1.0"
ANALYSIS_SCHEMA_VERSION = 2
ANALYZER_VERSION = "benchmark-1.0"
CONFIG_HASH = "b" * 64
EXTRACTOR_VERSION = "benchmark-1.0"
NORMALIZATION_VERSION = "1"
TIMESTAMP = "2026-01-01T00:00:00+00:00"
CHUNK_SIZE = 1_000


def build_catalog(path: Path, *, tracks: int, analyses_per_track: int) -> Path:
    """Create a fresh migrated catalog with deterministic benchmark history."""
    if tracks < 0:
        raise ValueError("tracks must not be negative")
    if analyses_per_track < 1:
        raise ValueError("analyses_per_track must be positive")
    if path.exists():
        raise FileExistsError(f"benchmark catalog already exists: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    database = Database(connection)
    try:
        database.migrate()
        with database.transaction():
            _insert_source_and_scan(connection, tracks)
            _insert_tracks(connection, tracks)
            _insert_directories(connection, tracks)
            _insert_artifacts(connection, tracks)
            _insert_metadata(connection, tracks)
            _insert_technical_metadata(connection, tracks)
            _insert_analysis_runs(connection, tracks, analyses_per_track)
            _insert_analysis_history(connection, tracks, analyses_per_track)
            _insert_events(connection, tracks, analyses_per_track)
    finally:
        connection.close()
    return path


def _insert_source_and_scan(connection: sqlite3.Connection, tracks: int) -> None:
    connection.execute(
        """
        INSERT INTO library_sources (
            source_id, root_path, set_eligible, analyze, enabled, created_at, updated_at
        ) VALUES (?, ?, 1, 1, 1, ?, ?)
        """,
        (SOURCE_ID, "/benchmark/library", TIMESTAMP, TIMESTAMP),
    )
    connection.execute(
        """
        INSERT INTO scan_runs (
            id, source_id, started_at, finished_at, status, files_seen, audio_seen,
            artifacts_seen, scanner_version
        ) VALUES (1, ?, ?, ?, 'succeeded', ?, ?, ?, ?)
        """,
        (SOURCE_ID, TIMESTAMP, TIMESTAMP, tracks, tracks, _artifact_count(tracks), SCANNER_VERSION),
    )
    connection.execute(
        "UPDATE library_sources SET last_successful_scan_id = 1 WHERE source_id = ?",
        (SOURCE_ID,),
    )


def _insert_tracks(connection: sqlite3.Connection, tracks: int) -> None:
    sql = """
        INSERT INTO tracks (
            id, source_id, relative_path, filename, extension, size_bytes, mtime_ns,
            presence_status, discovered_at, last_seen_at, created_scan_id, last_seen_scan_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'present', ?, ?, 1, 1)
    """

    def rows() -> Iterable[tuple[object, ...]]:
        for track_id in range(1, tracks + 1):
            relative_path = _relative_path(track_id)
            yield (
                track_id,
                SOURCE_ID,
                relative_path,
                Path(relative_path).name,
                ".flac",
                _size_bytes(track_id),
                _mtime_ns(track_id),
                TIMESTAMP,
                TIMESTAMP,
            )

    _executemany_in_chunks(connection, sql, rows())


def _insert_directories(connection: sqlite3.Connection, tracks: int) -> None:
    sql = """
        INSERT INTO directories (
            id, source_id, relative_path, presence_status, discovered_at, last_seen_at,
            last_seen_scan_id
        ) VALUES (?, ?, ?, 'present', ?, ?, 1)
    """
    rows = (
        (directory_id, SOURCE_ID, f"Library/{track_id // 1_000:03d}", TIMESTAMP, TIMESTAMP)
        for directory_id, track_id in enumerate(range(1, tracks + 1, 1_000), start=1)
    )
    _executemany_in_chunks(connection, sql, rows)


def _insert_artifacts(connection: sqlite3.Connection, tracks: int) -> None:
    sql = """
        INSERT INTO library_artifacts (
            id, source_id, relative_path, artifact_type, size_bytes, mtime_ns,
            presence_status, first_seen_at, last_seen_at, last_seen_scan_id
        ) VALUES (?, ?, ?, 'playlist', ?, ?, 'present', ?, ?, 1)
    """
    rows = (
        (
            artifact_id,
            SOURCE_ID,
            f"Playlists/list-{track_id:09d}.m3u8",
            1_024 + artifact_id,
            _mtime_ns(track_id),
            TIMESTAMP,
            TIMESTAMP,
        )
        for artifact_id, track_id in enumerate(range(1, tracks + 1, 20), start=1)
    )
    _executemany_in_chunks(connection, sql, rows)


def _insert_metadata(connection: sqlite3.Connection, tracks: int) -> None:
    sql = """
        INSERT INTO embedded_metadata (
            track_id, title, artist, metadata_extracted_at, extractor_version,
            input_size_bytes, input_mtime_ns, normalization_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    def rows() -> Iterable[tuple[object, ...]]:
        for track_id in range(1, tracks + 1):
            current = track_id % 2 == 0
            yield (
                track_id,
                f"Benchmark Track {track_id:09d}",
                f"Benchmark Artist {track_id % 100:03d}",
                TIMESTAMP,
                EXTRACTOR_VERSION,
                _size_bytes(track_id) if current else _size_bytes(track_id) - 1,
                _mtime_ns(track_id) if current else _mtime_ns(track_id) - 1,
                NORMALIZATION_VERSION,
            )

    _executemany_in_chunks(connection, sql, rows())


def _insert_technical_metadata(connection: sqlite3.Connection, tracks: int) -> None:
    sql = """
        INSERT INTO technical_audio_metadata (
            track_id, duration_seconds, sample_rate, channels, codec, container, bitrate,
            lossless, probe_version, probed_at
        ) VALUES (?, ?, ?, 2, 'flac', 'flac', ?, 1, ?, ?)
    """
    rows = (
        (
            track_id,
            180.0 + (track_id % 300),
            44_100 if track_id % 2 else 48_000,
            900_000 + (track_id % 100_000),
            ANALYZER_VERSION,
            TIMESTAMP,
        )
        for track_id in range(1, tracks + 1)
    )
    _executemany_in_chunks(connection, sql, rows)


def _insert_analysis_runs(
    connection: sqlite3.Connection, tracks: int, analyses_per_track: int
) -> None:
    sql = """
        INSERT INTO analysis_runs (
            id, started_at, finished_at, status, eligible, analyzed, reused, failed,
            analysis_schema_version, analyzer_version, config_hash
        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
    """

    def rows() -> Iterable[tuple[object, ...]]:
        for attempt in range(1, analyses_per_track + 1):
            succeeded = _attempt_succeeded(attempt, analyses_per_track)
            yield (
                attempt,
                TIMESTAMP,
                TIMESTAMP,
                "succeeded" if succeeded else "failed",
                tracks,
                tracks if succeeded else 0,
                0 if succeeded else tracks,
                ANALYSIS_SCHEMA_VERSION,
                ANALYZER_VERSION,
                CONFIG_HASH,
            )

    _executemany_in_chunks(connection, sql, rows())


def _insert_analysis_history(
    connection: sqlite3.Connection, tracks: int, analyses_per_track: int
) -> None:
    sql = """
        INSERT INTO audio_analysis (
            id, track_id, analysis_run_id, analysis_schema_version, analyzer_version,
            config_hash, input_size_bytes, input_mtime_ns, analysis_status,
            analysis_confidence, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    def rows() -> Iterable[tuple[object, ...]]:
        for track_id in range(1, tracks + 1):
            for attempt in range(1, analyses_per_track + 1):
                succeeded = _attempt_succeeded(attempt, analyses_per_track)
                payload: dict[str, object]
                if succeeded:
                    payload = {
                        "attempt": attempt,
                        "bpm": 120.0 + (track_id % 20),
                        "key": f"{((track_id - 1) % 12) + 1}A",
                    }
                else:
                    payload = {"attempt": attempt, "error": "benchmark failure"}
                yield (
                    _analysis_id(track_id, attempt, analyses_per_track),
                    track_id,
                    attempt,
                    ANALYSIS_SCHEMA_VERSION,
                    ANALYZER_VERSION,
                    CONFIG_HASH,
                    _size_bytes(track_id),
                    _mtime_ns(track_id),
                    "succeeded" if succeeded else "failed",
                    0.9 if succeeded else None,
                    json.dumps(payload, separators=(",", ":")),
                    TIMESTAMP,
                )

    _executemany_in_chunks(connection, sql, rows())


def _insert_events(connection: sqlite3.Connection, tracks: int, analyses_per_track: int) -> None:
    sql = """
        INSERT INTO track_events (
            id, track_id, occurred_at, scan_run_id, analysis_run_id, event_type, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """

    def rows() -> Iterable[tuple[object, ...]]:
        for track_id in range(1, tracks + 1):
            analysis_id = _analysis_id(track_id, analyses_per_track, analyses_per_track)
            yield (
                (track_id * 2) - 1,
                track_id,
                TIMESTAMP,
                1,
                None,
                "track_discovered",
                json.dumps({"path": _relative_path(track_id)}, separators=(",", ":")),
            )
            yield (
                track_id * 2,
                track_id,
                TIMESTAMP,
                None,
                analyses_per_track,
                "analysis_completed",
                json.dumps({"analysis_id": analysis_id}, separators=(",", ":")),
            )

    _executemany_in_chunks(connection, sql, rows())


def _executemany_in_chunks(
    connection: sqlite3.Connection,
    sql: str,
    rows: Iterable[tuple[object, ...]],
    *,
    chunk_size: int = CHUNK_SIZE,
) -> None:
    batch: list[tuple[object, ...]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == chunk_size:
            connection.executemany(sql, batch)
            batch.clear()
    if batch:
        connection.executemany(sql, batch)


def _attempt_succeeded(attempt: int, analyses_per_track: int) -> bool:
    return (analyses_per_track - attempt) % 2 == 0


def _analysis_id(track_id: int, attempt: int, analyses_per_track: int) -> int:
    return ((track_id - 1) * analyses_per_track) + attempt


def _relative_path(track_id: int) -> str:
    return f"Library/{(track_id - 1) // 1_000:03d}/track-{track_id:09d}.flac"


def _size_bytes(track_id: int) -> int:
    return 10_000_000 + track_id


def _mtime_ns(track_id: int) -> int:
    return 1_700_000_000_000_000_000 + track_id


def _artifact_count(tracks: int) -> int:
    return 0 if tracks == 0 else ((tracks - 1) // 20) + 1
