import csv
import sqlite3
from pathlib import Path

import pytest

from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.analysis.extractor import AnalysisExtractionResult
from dj_digger.analysis.persistence import AnalysisOutcome, AnalysisPersistence
from dj_digger.catalog.current_analysis import CurrentAnalysisProjector
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    catalog = Database.open(tmp_path / "catalog.sqlite")
    catalog.migrate()
    return catalog


@pytest.fixture
def track(database: Database) -> Track:
    with database.transaction():
        SourceRepository(database).upsert(
            "source", Path("/music"), set_eligible=True, analyze=True, enabled=True
        )
    scan_id = ScanRunRepository(database).start("source", scanner_version="test")
    with database.transaction():
        return TrackRepository(database).insert(
            source_id="source",
            relative_path="Techno/A.flac",
            filename="A.flac",
            extension=".flac",
            size_bytes=10,
            mtime_ns=20,
            scan_id=scan_id,
        )


def _identity(config_hash: str = "a" * 64) -> AnalysisIdentity:
    return AnalysisIdentity(2, "analyzer/2", config_hash)


def _success(
    database: Database,
    track: Track,
    *,
    occurred_at: str,
    bpm: float,
    key: str,
) -> tuple[int, int]:
    persistence = AnalysisPersistence(database)
    identity = _identity()
    run_id = persistence.start_run(identity, eligible=1, reused=0, started_at=occurred_at)
    extraction = AnalysisExtractionResult(
        {
            "bpm": bpm,
            "bpm_confidence": 0.91,
            "beat_stability": 0.82,
            "key": key,
            "key_confidence": 0.73,
            "sub_energy": 0.64,
            "low_energy": 0.55,
            "low_mid_energy": 0.46,
        },
        {"sections": [{"start": 0.0, "end": 8.0}]},
        0.88,
        "succeeded",
    )
    assert persistence.persist_outcome(
        run_id,
        identity,
        AnalysisOutcome(track, extraction, None, "aggregation"),
        occurred_at=occurred_at,
    ) == (1, 0)
    persistence.finish_run(run_id, finished_at=occurred_at)
    analysis_id = int(
        database.scalar("SELECT MAX(id) FROM audio_analysis WHERE analysis_run_id = ?", (run_id,))
    )
    return run_id, analysis_id


def _failure(database: Database, track: Track, *, occurred_at: str) -> tuple[int, int]:
    persistence = AnalysisPersistence(database)
    identity = _identity()
    run_id = persistence.start_run(identity, eligible=1, reused=0, started_at=occurred_at)
    assert persistence.persist_outcome(
        run_id,
        identity,
        AnalysisOutcome(track, {}, "controlled failure", "decode"),
        occurred_at=occurred_at,
    ) == (0, 1)
    persistence.finish_run(run_id, finished_at=occurred_at)
    analysis_id = int(
        database.scalar("SELECT MAX(id) FROM audio_analysis WHERE analysis_run_id = ?", (run_id,))
    )
    return run_id, analysis_id


def _projections(database: Database) -> list[tuple[object, ...]]:
    return database.execute(
        """SELECT track_id, audio_analysis_id, analysis_schema_version, analyzer_version,
                  config_hash, analysis_confidence, bpm, bpm_confidence, beat_stability,
                  key, key_confidence, sub_energy, low_energy, low_mid_energy, updated_at
           FROM current_track_analysis
           ORDER BY track_id"""
    ).fetchall()


def _projection(database: Database) -> tuple[object, ...] | None:
    rows = _projections(database)
    return rows[0] if rows else None


def test_first_success_atomically_persists_history_details_event_counter_and_projection(
    database: Database, track: Track
) -> None:
    run_id, analysis_id = _success(
        database, track, occurred_at="2026-08-27T10:00:00+00:00", bpm=128.0, key="8A"
    )

    assert _projection(database) == (
        track.id,
        analysis_id,
        2,
        "analyzer/2",
        "a" * 64,
        0.88,
        128.0,
        0.91,
        0.82,
        "8A",
        0.73,
        0.64,
        0.55,
        0.46,
        "2026-08-27T10:00:00+00:00",
    )
    assert database.scalar("SELECT COUNT(*) FROM audio_analysis") == 1
    assert database.scalar("SELECT COUNT(*) FROM track_sections") == 1
    assert database.execute(
        "SELECT event_type FROM track_events WHERE analysis_run_id = ?", (run_id,)
    ).fetchone() == ("analysis_completed",)
    assert database.execute(
        "SELECT analyzed, failed FROM analysis_runs WHERE id = ?", (run_id,)
    ).fetchone() == (1, 0)


def test_newer_success_replaces_projection_but_newer_failure_does_not(
    database: Database, track: Track
) -> None:
    _, first_id = _success(database, track, occurred_at="one", bpm=125.0, key="7A")
    _, second_id = _success(database, track, occurred_at="two", bpm=130.0, key="9A")

    assert second_id > first_id
    assert _projection(database)[1:] == (
        second_id,
        2,
        "analyzer/2",
        "a" * 64,
        0.88,
        130.0,
        0.91,
        0.82,
        "9A",
        0.73,
        0.64,
        0.55,
        0.46,
        "two",
    )

    _, failure_id = _failure(database, track, occurred_at="three")

    assert failure_id > second_id
    assert _projection(database)[1] == second_id
    assert database.scalar("SELECT COUNT(*) FROM audio_analysis") == 3


def test_track_projection_cascades_after_history_is_explicitly_removed(
    database: Database, track: Track
) -> None:
    _, analysis_id = _success(database, track, occurred_at="one", bpm=128.0, key="8A")

    database.execute("PRAGMA defer_foreign_keys = ON")
    with database.transaction():
        database.execute("DELETE FROM track_events WHERE track_id = ?", (track.id,))
        database.execute("DELETE FROM audio_analysis WHERE id = ?", (analysis_id,))
        database.execute("DELETE FROM tracks WHERE id = ?", (track.id,))

    assert database.scalar("SELECT COUNT(*) FROM current_track_analysis") == 0
    assert database.scalar("SELECT COUNT(*) FROM tracks") == 0


def test_rebuild_is_deterministic_idempotent_and_matches_incremental_projection(
    database: Database, track: Track
) -> None:
    _success(database, track, occurred_at="2099-later-time", bpm=125.0, key="7A")
    _, latest_success_id = _success(
        database, track, occurred_at="1900-earlier-time", bpm=130.0, key="9A"
    )
    _failure(database, track, occurred_at="three")
    scan_id = int(database.scalar("SELECT MAX(id) FROM scan_runs"))
    with database.transaction():
        second_track = TrackRepository(database).insert(
            source_id="source",
            relative_path="Techno/B.flac",
            filename="B.flac",
            extension=".flac",
            size_bytes=11,
            mtime_ns=21,
            scan_id=scan_id,
        )
    _success(database, second_track, occurred_at="four", bpm=135.0, key="10A")
    incremental = _projections(database)
    database.execute("DELETE FROM current_track_analysis")
    database.commit()

    projector = CurrentAnalysisProjector(database)
    assert projector.rebuild() == 2
    assert _projections(database) == incremental
    assert _projection(database)[1] == latest_success_id

    assert projector.rebuild() == 2
    assert _projections(database) == incremental
    assert database.scalar("SELECT COUNT(*) FROM audio_analysis") == 4


def test_projection_failure_rolls_back_attempt_sections_event_and_counter(
    database: Database, track: Track
) -> None:
    database.execute(
        """CREATE TRIGGER reject_current_projection
           BEFORE INSERT ON current_track_analysis
           BEGIN SELECT RAISE(FAIL, 'projection rejected'); END"""
    )
    database.commit()
    persistence = AnalysisPersistence(database)
    identity = _identity()
    run_id = persistence.start_run(identity, eligible=1, reused=0, started_at="start")
    extraction = AnalysisExtractionResult(
        {"bpm": 128.0},
        {"sections": [{"start": 0.0, "end": 8.0}]},
        0.75,
        "succeeded",
    )

    with pytest.raises(sqlite3.IntegrityError, match="projection rejected"):
        persistence.persist_outcome(
            run_id,
            identity,
            AnalysisOutcome(track, extraction, None, "aggregation"),
            occurred_at="one",
        )

    assert database.execute(
        "SELECT analyzed, failed FROM analysis_runs WHERE id = ?", (run_id,)
    ).fetchone() == (0, 0)
    for table in (
        "audio_analysis",
        "track_sections",
        "track_events",
        "current_track_analysis",
    ):
        assert database.scalar(f"SELECT COUNT(*) FROM {table}") == 0


def test_latest_attempt_export_remains_failed_while_projection_keeps_latest_success(
    database: Database, track: Track, tmp_path: Path
) -> None:
    from dj_digger.analysis.exporters import AnalysisExporter

    _, success_id = _success(database, track, occurred_at="one", bpm=128.0, key="8A")
    _failure(database, track, occurred_at="two")

    AnalysisExporter(database).export(tmp_path / "export")

    rows = list(
        csv.DictReader(
            (tmp_path / "export" / "dj-analysis.tsv").open(encoding="utf-8", newline=""),
            delimiter="\t",
        )
    )
    assert len(rows) == 1
    assert rows[0]["analysis_status"] == "failed"
    assert _projection(database)[1] == success_id
