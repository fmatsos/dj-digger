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


def identity(config_hash: str) -> AnalysisIdentity:
    return AnalysisIdentity(schema_version=2, analyzer_version="1.0.0", config_hash=config_hash)


def test_incremental_lifecycle_persists_outcome_and_derives_interrupted_status(
    database, track
) -> None:
    from dj_digger.analysis.extractor import AnalysisExtractionResult
    from dj_digger.analysis.persistence import AnalysisOutcome, AnalysisPersistence

    persistence = AnalysisPersistence(database)
    ident = identity("d" * 64)
    run_id = persistence.start_run(ident, eligible=2, reused=0, started_at="start")
    extraction = AnalysisExtractionResult(
        {"bpm": 128.0}, {"sections": [{"start": 0.0, "end": 8.0}]}, 0.75, "succeeded"
    )

    assert persistence.persist_outcome(
        run_id,
        ident,
        AnalysisOutcome(track, extraction, None, "aggregation"),
        occurred_at="one",
    ) == (1, 0)
    assert database.execute(
        "SELECT started_at, finished_at, status, eligible, analyzed, reused, failed "
        "FROM analysis_runs WHERE id = ?",
        (run_id,),
    ).fetchone() == ("start", None, "running", 2, 1, 0, 0)
    attempt = database.execute(
        "SELECT analysis_status, analysis_confidence, payload_json, created_at "
        "FROM audio_analysis WHERE analysis_run_id = ?",
        (run_id,),
    ).fetchone()
    assert attempt[:2] == ("succeeded", 0.75)
    assert json.loads(attempt[2]) == {"bpm": 128.0}
    assert attempt[3] == "one"
    assert json.loads(database.scalar("SELECT payload_json FROM track_sections")) == {
        "end": 8.0,
        "start": 0.0,
    }
    event = database.execute(
        "SELECT event_type, occurred_at, payload_json FROM track_events"
    ).fetchone()
    assert event[:2] == ("analysis_completed", "one")
    assert json.loads(event[2]) == {"analysis_id": 1}

    assert persistence.finish_run(run_id, finished_at="finish") == ("partial", 1, 0)
    assert database.execute(
        "SELECT finished_at, status, analyzed, failed FROM analysis_runs WHERE id = ?",
        (run_id,),
    ).fetchone() == ("finish", "partial", 1, 0)


def test_incremental_outcome_rolls_back_attempt_sections_event_and_counter(
    database, track
) -> None:
    from dj_digger.analysis.extractor import AnalysisExtractionResult
    from dj_digger.analysis.persistence import AnalysisOutcome, AnalysisPersistence

    persistence = AnalysisPersistence(database)
    ident = identity("e" * 64)
    run_id = persistence.start_run(ident, eligible=1, reused=0, started_at="start")
    extraction = AnalysisExtractionResult(
        {"bpm": 128.0}, {"sections": ["not an object"]}, None, "succeeded"
    )

    with pytest.raises(ValueError, match="analysis section must be an object"):
        persistence.persist_outcome(
            run_id,
            ident,
            AnalysisOutcome(track, extraction, None, "aggregation"),
            occurred_at="one",
        )

    assert database.execute(
        "SELECT status, analyzed, failed FROM analysis_runs WHERE id = ?", (run_id,)
    ).fetchone() == ("running", 0, 0)
    for table in ("audio_analysis", "track_sections", "track_events"):
        assert database.scalar(f"SELECT COUNT(*) FROM {table}") == 0


@pytest.mark.parametrize(
    ("eligible", "reused", "outcome_kind", "expected"),
    [
        (1, 0, "success", ("succeeded", 1, 0)),
        (2, 0, "success", ("partial", 1, 0)),
        (2, 1, "failure", ("partial", 0, 1)),
        (2, 0, "failure", ("failed", 0, 1)),
    ],
    ids=["complete-success", "success-unaccounted", "reuse-failure", "failure-only"],
)
def test_reconcile_running_run_refreshes_attempt_counters_without_new_history(
    database, track, eligible: int, reused: int, outcome_kind: str, expected: tuple[str, int, int]
) -> None:
    from dj_digger.analysis.persistence import AnalysisOutcome, AnalysisPersistence

    persistence = AnalysisPersistence(database)
    ident = identity("f" * 64)
    run_id = persistence.start_run(
        ident, eligible=eligible, reused=reused, started_at="start"
    )
    if outcome_kind == "success":
        outcome = AnalysisOutcome(track, {"bpm": 128.0}, None, "aggregation")
    else:
        outcome = AnalysisOutcome(track, {}, "controlled failure", "decode")
    persistence.persist_outcome(run_id, ident, outcome, occurred_at="one")
    database.execute(
        "UPDATE analysis_runs SET analyzed = 99, failed = 98 WHERE id = ?", (run_id,)
    )
    database.commit()
    attempts_before = database.scalar("SELECT COUNT(*) FROM audio_analysis")
    events_before = database.scalar("SELECT COUNT(*) FROM track_events")

    assert persistence.reconcile_running_runs(finished_at="interrupted") == 1
    assert database.execute(
        "SELECT status, analyzed, failed, reused, finished_at FROM analysis_runs WHERE id = ?",
        (run_id,),
    ).fetchone() == (*expected, reused, "interrupted")
    assert database.scalar("SELECT COUNT(*) FROM audio_analysis") == attempts_before
    assert database.scalar("SELECT COUNT(*) FROM track_events") == events_before

    assert persistence.reconcile_running_runs(finished_at="later") == 0
    assert database.execute(
        "SELECT status, analyzed, failed, reused, finished_at FROM analysis_runs WHERE id = ?",
        (run_id,),
    ).fetchone() == (*expected, reused, "interrupted")
