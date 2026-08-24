import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository


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
            "database = Database.open(Path('catalog.sqlite')); "
            "database.migrate(); "
            "assert database.table_exists('tracks')",
        ],
        check=False,
        cwd=tmp_path,
        env={"PYTHONPATH": str(isolated_package)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_catalog_migration_is_idempotent_after_reopening(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite"
    database = Database.open(database_path)
    database.migrate()
    database.migrate()

    assert database.scalar("PRAGMA user_version") == 1
    assert database.scalar("PRAGMA foreign_keys") == 1
    assert database.table_exists("tracks")
    assert database.table_exists("track_events")

    reopened = Database.open(database_path)
    reopened.migrate()
    assert reopened.scalar("PRAGMA user_version") == 1
    assert reopened.table_exists("library_sources")


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
