import sqlite3
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.read_repositories import LibraryReadRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    catalog = Database.open(tmp_path / "catalog.sqlite")
    catalog.migrate()
    with catalog.transaction():
        catalog.execute(
            """
            INSERT INTO library_sources (
                source_id, root_path, set_eligible, analyze, enabled, created_at, updated_at
            ) VALUES ('source', '/music', 0, 1, 1, 'now', 'now')
            """
        )
        catalog.execute(
            """
            INSERT INTO scan_runs (id, source_id, started_at, status, scanner_version)
            VALUES (1, 'source', 'now', 'succeeded', 'test')
            """
        )
        catalog.execute(
            """
            INSERT INTO tracks (
                id, source_id, relative_path, filename, extension, size_bytes, mtime_ns,
                presence_status, discovered_at, last_seen_at, created_scan_id, last_seen_scan_id
            ) VALUES
                (10, 'source', 'A.flac', 'A.flac', '.FLAC', 100, 200,
                 'present', 'now', 'now', 1, 1),
                (11, 'source', 'missing.flac', 'missing.flac', '.flac', 101, 201,
                 'missing', 'now', 'now', 1, 1)
            """
        )
        catalog.execute(
            """
            INSERT INTO embedded_metadata (
                track_id, title, artist, metadata_extracted_at, extractor_version
            ) VALUES (10, 'Title', NULL, 'now', 'test')
            """
        )
        catalog.execute(
            """
            INSERT INTO technical_audio_metadata (
                track_id, duration_seconds, sample_rate, channels, codec, container,
                bitrate, lossless, loudness_lufs, true_peak_db, dynamic_range,
                probe_version, probed_at
            ) VALUES (10, 123.5, 48000, 2, NULL, 'flac', 900000, 1,
                      -10.5, -1.0, 8.0, 'test', 'now')
            """
        )
        catalog.execute(
            """
            INSERT INTO analysis_runs (
                id, started_at, status, analysis_schema_version, analyzer_version, config_hash
            ) VALUES (1, 'now', 'succeeded', 2, 'analyzer/2', 'hash')
            """
        )
        catalog.execute(
            """
            INSERT INTO audio_analysis (
                id, track_id, analysis_run_id, analysis_schema_version, analyzer_version,
                config_hash, input_size_bytes, input_mtime_ns, analysis_status,
                analysis_confidence, payload_json, created_at
            ) VALUES (20, 10, 1, 2, 'analyzer/2', 'hash', 100, 200,
                      'succeeded', 0.9, '{}', 'now')
            """
        )
        catalog.execute(
            """
            INSERT INTO current_track_analysis (
                track_id, audio_analysis_id, analysis_schema_version, analyzer_version,
                config_hash, analysis_confidence, bpm, bpm_confidence, beat_stability,
                key, key_confidence, sub_energy, low_energy, low_mid_energy, updated_at
            ) VALUES (10, 20, 2, 'analyzer/2', 'hash', 0.9, 128.0, 0.8, 0.7,
                      NULL, NULL, 0.6, 0.5, 0.4, 'now')
            """
        )
    return catalog


def test_list_tracks_reads_present_view_projection_with_nulls_and_distinct_source_flags(
    database: Database,
) -> None:
    rows = LibraryReadRepository(database).list_tracks(limit=10)
    columns = tuple(
        row[1] for row in database.execute("PRAGMA table_info(library_tracks)").fetchall()
    )

    assert len(rows) == 1
    row = dict(zip(columns, rows[0], strict=True))
    assert row["track_id"] == 10
    assert row["relative_path"] == "A.flac"
    assert row["set_eligible"] == 0
    assert row["analysis_enabled"] == 1
    assert row["title"] == "Title"
    assert row["artist"] is None
    assert row["duration_seconds"] == 123.5
    assert row["codec"] is None
    assert row["loudness_lufs"] == -10.5
    assert row["audio_analysis_id"] == 20
    assert row["bpm"] == 128.0
    assert row["key"] is None
    assert row["low_mid_energy"] == 0.4


def test_list_tracks_uses_track_id_keyset_pagination(database: Database) -> None:
    with database.transaction():
        database.execute(
            """
            INSERT INTO tracks (
                id, source_id, relative_path, filename, extension, size_bytes, mtime_ns,
                presence_status, discovered_at, last_seen_at, created_scan_id, last_seen_scan_id
            ) VALUES (12, 'source', '0-before-by-path.flac', '0-before-by-path.flac',
                      '.flac', 102, 202, 'present', 'now', 'now', 1, 1)
            """
        )

    repository = LibraryReadRepository(database)

    assert [row[0] for row in repository.list_tracks(limit=1)] == [10]
    assert [row[0] for row in repository.list_tracks(limit=1, after_track_id=10)] == [12]
    assert repository.list_tracks(limit=1, after_track_id=12) == []


@pytest.mark.parametrize("limit", [0, 1001])
def test_list_tracks_rejects_limits_outside_public_bounds(database: Database, limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
        LibraryReadRepository(database).list_tracks(limit=limit)


def test_export_rows_preserves_public_tuple_and_order(database: Database) -> None:
    assert LibraryReadRepository(database).export_rows() == [
        (
            10,
            "source",
            "A.flac",
            "A.flac",
            ".FLAC",
            100,
            200,
            0,
            "Title",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            123.5,
            48000,
            2,
            None,
            "flac",
            900000,
            1,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
    ]


def test_library_view_has_no_write_path(database: Database) -> None:
    with pytest.raises(sqlite3.OperationalError, match="cannot modify library_tracks"):
        database.execute("UPDATE library_tracks SET title = 'changed' WHERE track_id = 10")

    assert database.scalar("SELECT title FROM embedded_metadata WHERE track_id = 10") == "Title"
