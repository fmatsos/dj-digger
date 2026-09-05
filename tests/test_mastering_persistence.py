import sqlite3
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository
from dj_digger.duplicates.mastering import MASTERING_ANALYSIS_VERSION, MasteringMeasurements
from dj_digger.duplicates.mastering_repository import MasteringRepository


def _track(database: Database) -> Track:
    with database.transaction():
        SourceRepository(database).upsert(
            "source", Path("/music"), set_eligible=True, analyze=True, enabled=True
        )
    scan_id = ScanRunRepository(database).start("source", scanner_version="test")
    with database.transaction():
        return TrackRepository(database).insert(
            source_id="source",
            relative_path="track.wav",
            filename="track.wav",
            extension=".wav",
            size_bytes=10,
            mtime_ns=20,
            scan_id=scan_id,
        )


def test_newer_failure_keeps_latest_success(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    track = _track(database)
    repository = MasteringRepository(database)
    success_id = repository.persist_success(
        track, MASTERING_ANALYSIS_VERSION, MasteringMeasurements(-11, 4, -1, -10, -9, 10)
    )
    repository.persist_failure(track, "v1", "decode", "failed")
    assert repository.current_for_tracks([track.id])[track.id].analysis_id == success_id
    assert database.scalar("SELECT COUNT(*) FROM mastering_analysis") == 2


def test_current_projection_hides_stale_track_identity(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    track = _track(database)
    repository = MasteringRepository(database)
    repository.persist_success(
        track, MASTERING_ANALYSIS_VERSION, MasteringMeasurements(-11, 4, -1, -10, -9, 10)
    )
    database.execute("UPDATE tracks SET size_bytes = size_bytes + 1 WHERE id = ?", (track.id,))

    assert repository.current_for_tracks([track.id]) == {}


def test_reuse_requires_input_identity_and_version(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    track = _track(database)
    repository = MasteringRepository(database)
    repository.persist_success(track, "v1", MasteringMeasurements(-11, 4, -1, -10, -9, 10))
    assert repository.reusable(track, "v1") is not None
    assert repository.reusable(track, "v2") is None
    changed = Track(
        track.id,
        track.source_id,
        track.relative_path,
        track.filename,
        track.extension,
        11,
        track.mtime_ns,
        track.presence_status,
    )
    assert repository.reusable(changed, "v1") is None


def test_rebuild_dj_uses_targets_without_new_mastering_attempt(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    track = _track(database)
    repository = MasteringRepository(database)
    analysis_id = repository.persist_success(
        track,
        MASTERING_ANALYSIS_VERSION,
        MasteringMeasurements(-13, 4, -0.2, -12, -10, 12.8),
    )
    assert repository.rebuild_dj(-9, -1) == 1
    assert database.scalar("SELECT mastering_analysis_id FROM current_dj_analysis") == analysis_id
    assert database.scalar("SELECT required_gain_db FROM current_dj_analysis") == 4


def test_catalog_rejects_non_finite_mastering_metrics(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    track = _track(database)

    with pytest.raises(sqlite3.IntegrityError):
        repository = MasteringRepository(database)
        repository.persist_success(
            track,
            MASTERING_ANALYSIS_VERSION,
            MasteringMeasurements(float("inf"), 4, -1, -10, -9, 10),
        )
