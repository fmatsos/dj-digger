import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.migrations import migrate
from dj_digger.catalog.repositories import (
    ScanRunRepository,
    SourceRepository,
    TrackRepository,
)

V6_TABLES = (
    "library_sources",
    "scan_runs",
    "tracks",
    "directories",
    "embedded_metadata",
    "technical_audio_metadata",
    "library_artifacts",
    "analysis_runs",
    "audio_analysis",
    "track_sections",
    "track_events",
)


def _create_v6_catalog(path: Path, *, invalid_foreign_key: bool = False) -> None:
    root = Path(__file__).parents[1]
    connection = sqlite3.connect(path)
    connection.executescript((root / "schemas/catalog-v6.sql").read_text(encoding="utf-8"))
    connection.executescript(
        """
        INSERT INTO library_sources VALUES
            ('source', '/music', 1, 1, 1, '2026-01-01', '2026-01-02', 11);
        INSERT INTO scan_runs VALUES
            (11, 'source', '2026-01-01', '2026-01-02', 'succeeded', 3, 1, 1,
             NULL, NULL, 'scanner/6');
        INSERT INTO tracks VALUES
            (31, 'source', 'Artist/Track.flac', 'Track.flac', '.flac', 1234, 5678,
             'present', '2026-01-01', '2026-01-02', NULL, NULL, 11, 11);
        INSERT INTO directories VALUES
            (21, 'source', 'Artist', 'present', '2026-01-01', '2026-01-02', NULL, 11);
        INSERT INTO embedded_metadata VALUES
            (31, 'Track', 'Artist', 'Album Artist', 'Album', '1', '1', 'House', '2026',
             '2026', 'Composer', 'Comment', 126.0, '9A', 'Warmup', '2026-01-02',
             'exiftool/1', 1234, 5678, 'normalizer/1');
        INSERT INTO technical_audio_metadata VALUES
            (31, 300.0, 48000, 2, 'flac', 'flac', 1000000, 1, -9.5, -1.0, 8.0,
             'ffprobe/1', '2026-01-02');
        INSERT INTO library_artifacts VALUES
            (41, 'source', '_Serato_/crate', 'serato_crate', 12, 34, 'present',
             '2026-01-01', '2026-01-02', NULL, 11);
        INSERT INTO analysis_runs VALUES
            (50, '2026-01-01', '2026-01-01', 'succeeded', 1, 1, 0, 0,
             2, 'analyzer/1', 'old-hash'),
            (51, '2026-01-02', '2026-01-02', 'succeeded', 1, 1, 0, 0,
             2, 'analyzer/2', 'hash'),
            (52, '2026-01-03', '2026-01-03', 'failed', 1, 0, 0, 1,
             2, 'analyzer/2', 'hash');
        INSERT INTO audio_analysis VALUES
            (60, 31, 50, 2, 'analyzer/1', 'old-hash', 1234, 5678, 'succeeded', 0.4,
             '{"bpm":120.0,"key":"Cm"}', '2026-01-01T10:00:00Z'),
            (61, 31, 51, 2, 'analyzer/2', 'hash', 1234, 5678, 'succeeded', 0.81,
             '{"analysis_confidence":0.99,"bpm":126.0,"bpm_confidence":0.82,' ||
             '"beat_stability":0.91,"key":"Am","key_confidence":0.73,' ||
             '"sub_energy":0.2,"low_energy":0.3,"low_mid_energy":0.4}',
             '2026-01-02T10:00:00Z'),
            (62, 31, 52, 2, 'analyzer/2', 'hash', 1234, 5678, 'failed', NULL,
             '{"error":"native crash"}', '2026-01-03T10:00:00Z');
        INSERT INTO track_sections VALUES
            (71, 61, 0, '{"index":0,"start_seconds":0,"end_seconds":32}');
        INSERT INTO track_events VALUES
            (81, 31, '2026-01-02', 11, NULL, 'track_discovered', NULL),
            (82, 31, '2026-01-03', NULL, 52, 'analysis_failed', '{"error":"crash"}');
        PRAGMA user_version = 6;
        """
    )
    if invalid_foreign_key:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO track_events VALUES (83, 999, '2026-01-04', NULL, NULL, 'invalid', NULL)"
        )
        connection.commit()
    connection.close()


_V6_TECHNICAL_AUDIO_METADATA_COLUMNS = (
    "track_id, duration_seconds, sample_rate, channels, codec, container, bitrate, "
    "lossless, loudness_lufs, true_peak_db, dynamic_range, probe_version, probed_at"
)


V7_TABLES = V6_TABLES + ("current_track_analysis",)


def _create_v7_catalog(path: Path) -> None:
    root = Path(__file__).parents[1]
    connection = sqlite3.connect(path)
    connection.executescript((root / "schemas/catalog-v7.sql").read_text(encoding="utf-8"))
    connection.executescript(
        """
        INSERT INTO library_sources VALUES
            ('source', '/music', 1, 1, 1, '2026-01-01', '2026-01-02', 11);
        INSERT INTO scan_runs VALUES
            (11, 'source', '2026-01-01', '2026-01-02', 'succeeded', 3, 1, 1,
             NULL, NULL, 'scanner/7');
        INSERT INTO tracks VALUES
            (31, 'source', 'Artist/Track.flac', 'Track.flac', '.flac', 1234, 5678,
             'present', '2026-01-01', '2026-01-02', NULL, NULL, 11, 11);
        INSERT INTO directories VALUES
            (21, 'source', 'Artist', 'present', '2026-01-01', '2026-01-02', NULL, 11);
        INSERT INTO embedded_metadata VALUES
            (31, 'Track', 'Artist', 'Album Artist', 'Album', '1', '1', 'House', '2026',
             '2026', 'Composer', 'Comment', 126.0, '9A', 'Warmup', '2026-01-02',
             'exiftool/1', 1234, 5678, 'normalizer/1');
        INSERT INTO technical_audio_metadata VALUES
            (31, 300.0, 48000, 2, 'flac', 'flac', 1000000, 1, -9.5, -1.0, 8.0,
             'ffprobe/1', '2026-01-02');
        INSERT INTO library_artifacts VALUES
            (41, 'source', '_Serato_/crate', 'serato_crate', 12, 34, 'present',
             '2026-01-01', '2026-01-02', NULL, 11);
        INSERT INTO analysis_runs VALUES
            (51, '2026-01-02', '2026-01-02', 'succeeded', 1, 1, 0, 0,
             2, 'analyzer/2', 'hash');
        INSERT INTO audio_analysis VALUES
            (61, 31, 51, 2, 'analyzer/2', 'hash', 1234, 5678, 'succeeded', 0.81,
             '{"bpm":126.0,"key":"Am"}', '2026-01-02T10:00:00Z');
        INSERT INTO track_sections VALUES
            (71, 61, 0, '{"index":0,"start_seconds":0,"end_seconds":32}');
        INSERT INTO track_events VALUES
            (81, 31, '2026-01-02', 11, NULL, 'track_discovered', NULL);
        INSERT INTO current_track_analysis VALUES
            (31, 61, 2, 'analyzer/2', 'hash', 0.81, 126.0, 0.82, 0.91, 'Am', 0.73,
             0.2, 0.3, 0.4, '2026-01-02T10:00:00Z');
        PRAGMA user_version = 7;
        """
    )
    connection.close()


def _snapshot_v7_rows(connection: sqlite3.Connection) -> dict[str, list[tuple[object, ...]]]:
    return {
        table: connection.execute(
            f"SELECT {_V6_TECHNICAL_AUDIO_METADATA_COLUMNS} FROM {table} ORDER BY rowid"
            if table == "technical_audio_metadata"
            else f"SELECT * FROM {table} ORDER BY rowid"
        ).fetchall()
        for table in V7_TABLES
    }


def _snapshot_v6_rows(connection: sqlite3.Connection) -> dict[str, list[tuple[object, ...]]]:
    return {
        table: connection.execute(
            f"SELECT {_V6_TECHNICAL_AUDIO_METADATA_COLUMNS} FROM {table} ORDER BY rowid"
            if table == "technical_audio_metadata"
            else f"SELECT * FROM {table} ORDER BY rowid"
        ).fetchall()
        for table in V6_TABLES
    }


def _normalized_schema(connection: sqlite3.Connection) -> dict[tuple[str, str], str | None]:
    rows = connection.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE type IN ('table', 'index', 'view') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {
        (str(object_type), str(name)): (
            None
            if sql is None
            else " ".join(str(sql).split()).replace(" ,", ",").replace(" )", ")")
        )
        for object_type, name, sql in rows
    }


def test_current_schema_copy_matches_packaged_schema() -> None:
    root = Path(__file__).parents[1]
    assert (root / "schemas/catalog-v9.sql").read_bytes() == (
        root / "src/dj_digger/catalog/sql/catalog-v9.sql"
    ).read_bytes()


def test_wheel_migrates_without_the_checkout_schema(tmp_path: Path) -> None:
    distribution = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(distribution)],
        check=True,
        cwd=Path(__file__).parents[1],
    )
    wheel = next(distribution.glob("*.whl"))
    isolated_package = tmp_path / "installed"
    with zipfile.ZipFile(wheel) as archive:
        packaged_files = set(archive.namelist())
        assert "dj_digger/catalog/sql/catalog-v9.sql" in packaged_files
        assert "dj_digger/catalog/sql/migrate-v6-to-v7.sql" in packaged_files
        assert "dj_digger/catalog/sql/migrate-v8-to-v9.sql" in packaged_files
        archive.extractall(isolated_package)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "from dj_digger.catalog.database import Database; "
            "from dj_digger.exports.audit import AuditExporter; "
            "from dj_digger.exports.tracks import TracksExporter; "
            "database = Database.open(Path('catalog.sqlite')); "
            "database.migrate(); "
            "assert database.table_exists('tracks'); "
            "TracksExporter(database).export(Path('tracks.tsv')); "
            "AuditExporter(database).export(Path('audit'))",
        ],
        check=False,
        cwd=tmp_path,
        env={"PYTHONPATH": str(isolated_package)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_isolated_wheel_upgrades_a_v6_catalog(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.sqlite"
    _create_v6_catalog(catalog_path)
    distribution = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(distribution)],
        check=True,
        cwd=Path(__file__).parents[1],
    )
    wheel = next(distribution.glob("*.whl"))
    isolated_package = tmp_path / "installed"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(isolated_package)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "from dj_digger.catalog.database import Database; "
            "database = Database.open(Path('catalog.sqlite')); "
            "database.migrate(); "
            "assert database.scalar('PRAGMA user_version') == 9; "
            "assert database.scalar('SELECT audio_analysis_id FROM current_track_analysis') == 61",
        ],
        check=False,
        cwd=tmp_path,
        env={"PYTHONPATH": str(isolated_package)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_wheel_contains_valid_analysis_schemas_outside_checkout(tmp_path: Path) -> None:
    distribution = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(distribution)],
        check=True,
        cwd=Path(__file__).parents[1],
    )
    wheel = next(distribution.glob("*.whl"))
    isolated = tmp_path / "installed"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(isolated)
    script = (
        "import importlib.resources as r; "
        "from jsonschema import Draft202012Validator; import json; "
        "base=r.files('dj_digger').joinpath('schemas'); "
        "[Draft202012Validator.check_schema(json.loads(base.joinpath(name).read_text())) "
        "for name in "
        "('dj-analysis.schema.json','dj-sections.schema.json','dj-analysis-run.schema.json')]"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={"PYTHONPATH": str(isolated)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_catalog_migration_is_idempotent_after_reopening(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite"
    database = Database.open(database_path)
    database.migrate()
    database.migrate()

    assert database.scalar("PRAGMA user_version") == 9
    assert database.scalar("PRAGMA foreign_keys") == 1
    assert database.table_exists("tracks")
    assert database.table_exists("track_events")

    reopened = Database.open(database_path)
    reopened.migrate()
    assert reopened.scalar("PRAGMA user_version") == 9
    assert reopened.table_exists("library_sources")


def test_current_sections_reference_current_analysis_table(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    foreign_keys = database.execute("PRAGMA foreign_key_list(track_sections)").fetchall()
    assert {row[2] for row in foreign_keys} == {"audio_analysis"}


def test_current_schema_has_embedded_metadata_input_facts(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()

    columns = {
        row[1]: row for row in database.execute("PRAGMA table_info(embedded_metadata)").fetchall()
    }

    assert database.scalar("PRAGMA user_version") == 9
    assert {"input_size_bytes", "input_mtime_ns", "normalization_version"} <= columns.keys()
    assert columns["input_size_bytes"][3] == 0
    assert columns["input_mtime_ns"][3] == 0
    assert columns["normalization_version"][3] == 0


def test_v6_upgrade_preserves_all_rows_and_backfills_latest_success(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    _create_v6_catalog(path)
    before_connection = sqlite3.connect(path)
    before = _snapshot_v6_rows(before_connection)
    before_connection.close()

    database = Database.open(path)
    database.migrate()

    assert _snapshot_v6_rows(database._connection) == before
    assert database.scalar("PRAGMA user_version") == 9
    assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    assert database.execute(
        "SELECT track_id, audio_analysis_id, analysis_schema_version, analyzer_version, "
        "config_hash, analysis_confidence, bpm, bpm_confidence, beat_stability, key, "
        "key_confidence, sub_energy, low_energy, low_mid_energy, updated_at "
        "FROM current_track_analysis"
    ).fetchone() == (
        31,
        61,
        2,
        "analyzer/2",
        "hash",
        0.81,
        126.0,
        0.82,
        0.91,
        "Am",
        0.73,
        0.2,
        0.3,
        0.4,
        "2026-01-02T10:00:00Z",
    )


def test_current_schema_has_duplicate_detection_tables(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()

    technical_columns = {
        row[1]: row
        for row in database.execute("PRAGMA table_info(technical_audio_metadata)").fetchall()
    }
    assert {"bit_depth", "input_size_bytes", "input_mtime_ns"} <= technical_columns.keys()
    assert technical_columns["bit_depth"][3] == 0
    assert technical_columns["input_size_bytes"][3] == 0
    assert technical_columns["input_mtime_ns"][3] == 0

    assert database.table_exists("audio_fingerprints")
    fingerprint_columns = {
        row[1] for row in database.execute("PRAGMA table_info(audio_fingerprints)").fetchall()
    }
    assert fingerprint_columns == {
        "track_id",
        "fingerprint",
        "fingerprint_hash",
        "fingerprint_version",
        "input_size_bytes",
        "input_mtime_ns",
        "fingerprinted_at",
    }
    assert (
        database.scalar(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' "
            "AND name = 'audio_fingerprints_group_idx'"
        )
        == 1
    )

    assert database.table_exists("duplicate_quality_selections")
    selection_columns = {
        row[1]
        for row in database.execute("PRAGMA table_info(duplicate_quality_selections)").fetchall()
    }
    assert selection_columns == {
        "source_id",
        "fingerprint_hash",
        "preferred_track_id",
        "ranking_version",
        "selected_at",
    }


def test_v7_upgrade_preserves_all_rows_and_adds_duplicate_schema(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    _create_v7_catalog(path)
    before_connection = sqlite3.connect(path)
    before = _snapshot_v7_rows(before_connection)
    before_connection.close()

    database = Database.open(path)
    database.migrate()

    assert _snapshot_v7_rows(database._connection) == before
    assert database.scalar("PRAGMA user_version") == 9
    assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    assert database.table_exists("audio_fingerprints")
    assert database.execute("SELECT * FROM audio_fingerprints").fetchall() == []
    assert database.table_exists("duplicate_quality_selections")
    assert database.execute("SELECT * FROM duplicate_quality_selections").fetchall() == []


def test_v6_upgrade_uses_begin_immediate_and_checks_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    _create_v6_catalog(path)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    statements: list[str] = []
    connection.set_trace_callback(statements.append)

    migrate(connection)

    normalized = [" ".join(statement.upper().split()) for statement in statements]
    begin = normalized.index("BEGIN IMMEDIATE")
    foreign_key_check = normalized.index("PRAGMA FOREIGN_KEY_CHECK")
    commit = normalized.index("COMMIT")
    assert begin < foreign_key_check < commit


def test_v6_upgrade_rolls_back_ddl_and_version_on_foreign_key_failure(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    _create_v6_catalog(path, invalid_foreign_key=True)
    database = Database.open(path)

    with pytest.raises(RuntimeError, match="foreign key check failed"):
        database.migrate()

    assert database.scalar("PRAGMA user_version") == 6
    assert not database.table_exists("current_track_analysis")
    assert (
        database.scalar(
            "SELECT 1 FROM sqlite_master WHERE type = 'view' AND name = 'library_tracks'"
        )
        is None
    )


def test_fresh_and_upgraded_catalogs_have_equivalent_application_schema(tmp_path: Path) -> None:
    fresh = Database.open(tmp_path / "fresh.sqlite")
    fresh.migrate()
    upgraded_path = tmp_path / "upgraded.sqlite"
    _create_v6_catalog(upgraded_path)
    upgraded = Database.open(upgraded_path)
    upgraded.migrate()

    assert _normalized_schema(fresh._connection) == _normalized_schema(upgraded._connection)


def test_current_schema_enforces_one_running_scan_per_source(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    sources = SourceRepository(database)
    with database.transaction():
        sources.upsert("djing", Path("/mnt/djing"), set_eligible=True, analyze=True, enabled=True)
        sources.upsert("music", Path("/mnt/music"), set_eligible=True, analyze=True, enabled=True)
    runs = ScanRunRepository(database)
    first = runs.start("djing", scanner_version="test")

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        runs.start("djing", scanner_version="test")
    runs.start("music", scanner_version="test")
    database.execute("UPDATE scan_runs SET status = 'failed' WHERE id = ?", (first,))
    database.commit()

    assert runs.start("djing", scanner_version="test") != first


def test_source_root_relocation_preserves_track_identity(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    sources = SourceRepository(database)
    with database.transaction():
        sources.upsert("djing", Path("/mnt/djing"), set_eligible=True, analyze=True, enabled=True)
    scan_id = ScanRunRepository(database).start("djing", scanner_version="test")
    tracks = TrackRepository(database)
    with database.transaction():
        track = tracks.insert(
            source_id="djing",
            relative_path="Techno/A.flac",
            filename="A.flac",
            extension=".flac",
            size_bytes=42,
            mtime_ns=123,
            scan_id=scan_id,
        )

    with database.transaction():
        sources.update_root("djing", Path("/srv/music/djing"))

    relocated = tracks.find("djing", "Techno/A.flac")
    assert relocated is not None
    assert relocated.id == track.id
    assert [present.id for present in tracks.present_for_source("djing")] == [track.id]


def test_tracks_are_unique_per_source_and_relative_path(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    with database.transaction():
        SourceRepository(database).upsert(
            "djing", Path("/mnt/djing"), set_eligible=True, analyze=True, enabled=True
        )
    scan_id = ScanRunRepository(database).start("djing", scanner_version="test")
    tracks = TrackRepository(database)
    track_kwargs = {
        "source_id": "djing",
        "relative_path": "Techno/A.flac",
        "filename": "A.flac",
        "extension": ".flac",
        "size_bytes": 42,
        "mtime_ns": 123,
        "scan_id": scan_id,
    }
    with database.transaction():
        tracks.insert(**track_kwargs)

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        with database.transaction():
            tracks.insert(**track_kwargs)


def test_source_scoped_observations_reject_a_scan_from_another_source(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    sources = SourceRepository(database)
    with database.transaction():
        sources.upsert("djing", Path("/mnt/djing"), set_eligible=True, analyze=True, enabled=True)
        sources.upsert("music", Path("/mnt/music"), set_eligible=True, analyze=True, enabled=True)
    foreign_scan_id = ScanRunRepository(database).start("music", scanner_version="test")

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        with database.transaction():
            TrackRepository(database).insert(
                source_id="djing",
                relative_path="Techno/A.flac",
                filename="A.flac",
                extension=".flac",
                size_bytes=42,
                mtime_ns=123,
                scan_id=foreign_scan_id,
            )

    observation_inserts = (
        (
            "directories",
            """
            INSERT INTO directories (
                source_id, relative_path, presence_status, discovered_at, last_seen_at,
                last_seen_scan_id
            ) VALUES ('djing', 'Techno', 'present', 'now', 'now', ?)
            """,
        ),
        (
            "library_artifacts",
            """
            INSERT INTO library_artifacts (
                source_id, relative_path, artifact_type, size_bytes, mtime_ns, presence_status,
                first_seen_at, last_seen_at, last_seen_scan_id
            ) VALUES ('djing', '_Serato_/crate', 'serato_crate', 1, 1, 'present', 'now', 'now', ?)
            """,
        ),
    )
    for _table, query in observation_inserts:
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            with database.transaction():
                database.execute(query, (foreign_scan_id,))
