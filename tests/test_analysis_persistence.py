import json
from pathlib import Path

import pytest

from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    catalog = Database.open(tmp_path / "catalog.sqlite")
    catalog.migrate()
    return catalog


@pytest.fixture
def track(database: Database):
    SourceRepository(database).upsert(
        "source", Path("/music"), set_eligible=True, analyze=True, enabled=True
    )
    scan_id = ScanRunRepository(database).start("source", scanner_version="test")
    return TrackRepository(database).insert(
        source_id="source",
        relative_path="Techno/A.flac",
        filename="A.flac",
        extension=".flac",
        size_bytes=10,
        mtime_ns=20,
        scan_id=scan_id,
    )


def identity(config_hash: str) -> AnalysisIdentity:
    return AnalysisIdentity(schema_version=2, analyzer_version="1.0.0", config_hash=config_hash)


def test_store_success_retains_versioned_history_and_emits_completed_event(database, track) -> None:
    from dj_digger.analysis.persistence import AnalysisPersistence

    persistence = AnalysisPersistence(database)
    first_id = persistence.store_success(track, identity("a" * 64), {"bpm": 128.0})
    second_id = persistence.store_success(track, identity("b" * 64), {"bpm": 130.0})

    assert first_id != second_id
    assert TrackRepository(database).analysis_history(track.id) == [
        (second_id, "succeeded", 10, 20, 2, "1.0.0", "b" * 64),
        (first_id, "succeeded", 10, 20, 2, "1.0.0", "a" * 64),
    ]
    event = database.execute(
        "SELECT track_id, analysis_run_id, payload_json FROM track_events "
        "WHERE event_type = 'analysis_completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert event[:2] == (track.id, 2)
    assert json.loads(event[2]) == {"analysis_id": second_id}


def test_store_failure_after_success_keeps_success_and_emits_failed_event(database, track) -> None:
    from dj_digger.analysis.persistence import AnalysisPersistence

    persistence = AnalysisPersistence(database)
    success_id = persistence.store_success(track, identity("a" * 64), {"bpm": 128.0})
    persistence.store_failure(track, identity("b" * 64), "decoder unavailable")

    assert database.execute(
        "SELECT id, analysis_status FROM audio_analysis WHERE track_id = ? ORDER BY id", (track.id,)
    ).fetchall() == [(success_id, "succeeded"), (success_id + 1, "failed")]
    event = database.execute(
        "SELECT track_id, analysis_run_id, payload_json FROM track_events "
        "WHERE event_type = 'analysis_failed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert event[:2] == (track.id, 2)
    assert json.loads(event[2]) == {"error": "decoder unavailable"}
