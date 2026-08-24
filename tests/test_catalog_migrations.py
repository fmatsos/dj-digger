import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository


def test_schema_copies_match_packaged_migrations() -> None:
    root = Path(__file__).parents[1]
    assert (root / "schemas/catalog-v1.sql").read_bytes() == (
        root / "src/dj_digger/catalog/sql/catalog-v1.sql"
    ).read_bytes()
    assert (root / "schemas/catalog-v3.sql").read_bytes() == (
        root / "src/dj_digger/catalog/sql/catalog-v3.sql"
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
            "AuditExporter(database).export(Path('audit'), legacy_compatibility=False)",
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
        [sys.executable, "-c", script], cwd=tmp_path, env={"PYTHONPATH": str(isolated)},
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_catalog_migration_is_idempotent_after_reopening(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite"
    database = Database.open(database_path)
    database.migrate()
    database.migrate()

    assert database.scalar("PRAGMA user_version") == 5
    assert database.scalar("PRAGMA foreign_keys") == 1
    assert database.table_exists("tracks")
    assert database.table_exists("track_events")

    reopened = Database.open(database_path)
    reopened.migrate()
    assert reopened.scalar("PRAGMA user_version") == 5
    assert reopened.table_exists("library_sources")


def test_v4_rebuild_does_not_leave_foreign_keys_referencing_old_analysis_table(
    tmp_path: Path,
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    stale = database.execute(
        "SELECT name, sql FROM sqlite_master WHERE sql LIKE '%audio_analysis_v4_old%'"
    ).fetchall()
    assert stale == []
    foreign_keys = database.execute("PRAGMA foreign_key_list(track_sections)").fetchall()
    assert {row[2] for row in foreign_keys} == {"audio_analysis"}


def test_v5_repairs_existing_v4_sections_fk_and_preserves_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite"
    database = Database.open(database_path)
    database.migrate()
    database._connection.close()
    database = Database.open(database_path)
    # Recreate the historical broken FK while retaining its data and v4 marker.
    database.execute(
        "INSERT INTO library_sources VALUES ('s', '/tmp', 1, 1, 1, 'now', 'now', NULL)"
    )
    database.execute(
        "INSERT INTO scan_runs (source_id, started_at, status, scanner_version) "
        "VALUES ('s', 'now', 'succeeded', 'test')"
    )
    database.execute(
        "INSERT INTO tracks VALUES (1, 's', 'a.wav', 'a.wav', '.wav', 1, 1, 'present', "
        "'now', 'now', NULL, NULL, 1, 1)"
    )
    database.execute(
        "INSERT INTO analysis_runs VALUES (1, 'now', 'now', 'succeeded', 1, 1, 0, 0, 2, 'a', 'b')"
    )
    database.execute(
        "INSERT INTO audio_analysis VALUES (1, 1, 1, 2, 'a', 'b', 1, 1, "
        "'succeeded', NULL, '{}', 'now')"
    )
    database.execute("PRAGMA foreign_keys = OFF")
    database.execute("ALTER TABLE track_sections RENAME TO track_sections_v4_old")
    database.execute(
        "CREATE TABLE track_sections (id INTEGER PRIMARY KEY, audio_analysis_id INTEGER NOT NULL "
        "REFERENCES audio_analysis_v4_old(id) ON DELETE CASCADE, section_index INTEGER NOT NULL, "
        "payload_json TEXT NOT NULL, UNIQUE(audio_analysis_id, section_index))"
    )
    database.execute("CREATE TABLE audio_analysis_v4_old (id INTEGER PRIMARY KEY)")
    database.execute("INSERT INTO audio_analysis_v4_old VALUES (1)")
    database.execute("INSERT INTO track_sections VALUES (1, 1, 7, '{}')")
    database.execute("DROP TABLE track_sections_v4_old")
    database.execute("PRAGMA user_version = 4")
    database.commit()
    database._connection.close()
    database = Database.open(database_path)
    database.migrate()
    assert database.scalar("PRAGMA user_version") == 5
    assert database.execute("SELECT section_index FROM track_sections").fetchone() == (7,)
    assert (
        database.execute("PRAGMA foreign_key_list(track_sections)").fetchone()[2]
        == "audio_analysis"
    )
    database.execute("DROP TABLE audio_analysis_v4_old")
    database.commit()
    assert (
        database.execute(
            "SELECT sql FROM sqlite_master WHERE sql LIKE '%audio_analysis_v4_old%'"
        ).fetchall()
        == []
    )


def test_v3_adds_embedded_metadata_input_facts_and_normalization_version(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()

    columns = {
        row[1]: row for row in database.execute("PRAGMA table_info(embedded_metadata)").fetchall()
    }

    assert database.scalar("PRAGMA user_version") == 5
    assert {"input_size_bytes", "input_mtime_ns", "normalization_version"} <= columns.keys()
    assert columns["input_size_bytes"][3] == 0
    assert columns["input_mtime_ns"][3] == 0
    assert columns["normalization_version"][3] == 0


def test_v2_enforces_one_running_scan_per_source(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    sources = SourceRepository(database)
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


def test_v2_migrates_legacy_duplicate_running_scans_deterministically(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite"
    connection = sqlite3.connect(database_path)
    v1_schema = Path(__file__).parents[1] / "src/dj_digger/catalog/sql/catalog-v1.sql"
    connection.executescript(v1_schema.read_text(encoding="utf-8") + "\nPRAGMA user_version = 1;")
    connection.executemany(
        """
        INSERT INTO library_sources (
            source_id, root_path, set_eligible, analyze, enabled, created_at, updated_at
        ) VALUES (?, ?, 1, 1, 1, 'created', 'updated')
        """,
        [("djing", "/mnt/djing"), ("music", "/mnt/music")],
    )
    connection.executemany(
        """
        INSERT INTO scan_runs (source_id, started_at, status, scanner_version)
        VALUES (?, '2026-08-24T00:00:00+00:00', 'running', 'v1')
        """,
        [("djing",), ("djing",), ("music",)],
    )
    connection.commit()
    connection.close()

    database = Database.open(database_path)
    database.migrate()

    assert database.scalar("PRAGMA user_version") == 5
    migrated_runs = database.execute(
        "SELECT id, status, finished_at, error_stage, error_message FROM scan_runs "
        "WHERE source_id = 'djing' ORDER BY id"
    ).fetchall()
    assert migrated_runs == [
        (
            1,
            "failed",
            migrated_runs[0][2],
            "migration",
            "superseded by V2 single-running invariant",
        ),
        (2, "running", None, None, None),
    ]
    finished_at = migrated_runs[0][2]
    assert isinstance(finished_at, str)
    assert datetime.fromisoformat(finished_at).tzinfo is not None
    assert database.execute(
        "SELECT status FROM scan_runs WHERE source_id = 'music'"
    ).fetchone() == ("running",)
    assert (
        database.scalar(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' "
            "AND name = 'scan_runs_one_running_per_source'"
        )
        == 1
    )
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        database.execute(
            "INSERT INTO scan_runs (source_id, started_at, status, scanner_version) "
            "VALUES ('djing', 'later', 'running', 'v2')"
        )


def test_source_root_relocation_preserves_track_identity(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    sources = SourceRepository(database)
    sources.upsert("djing", Path("/mnt/djing"), set_eligible=True, analyze=True, enabled=True)
    scan_id = ScanRunRepository(database).start("djing", scanner_version="test")
    tracks = TrackRepository(database)
    track = tracks.insert(
        source_id="djing",
        relative_path="Techno/A.flac",
        filename="A.flac",
        extension=".flac",
        size_bytes=42,
        mtime_ns=123,
        scan_id=scan_id,
    )

    sources.update_root("djing", Path("/srv/music/djing"))

    relocated = tracks.find("djing", "Techno/A.flac")
    assert relocated is not None
    assert relocated.id == track.id
    assert [present.id for present in tracks.present_for_source("djing")] == [track.id]


def test_tracks_are_unique_per_source_and_relative_path(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
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
    tracks.insert(**track_kwargs)

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        tracks.insert(**track_kwargs)


def test_source_scoped_observations_reject_a_scan_from_another_source(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    sources = SourceRepository(database)
    sources.upsert("djing", Path("/mnt/djing"), set_eligible=True, analyze=True, enabled=True)
    sources.upsert("music", Path("/mnt/music"), set_eligible=True, analyze=True, enabled=True)
    foreign_scan_id = ScanRunRepository(database).start("music", scanner_version="test")

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
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
            database.execute(query, (foreign_scan_id,))
