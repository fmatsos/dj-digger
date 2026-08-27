import sqlite3
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import SourceRepository
from dj_digger.scanning.lifecycle import ScanLifecycle
from dj_digger.scanning.scanner import ArtifactObservation, AudioObservation, ScanObservation


def observation(
    source_id: str,
    run_id: int,
    *,
    audio: dict[str, AudioObservation] | None = None,
    directories: set[str] | None = None,
    artifacts: dict[str, ArtifactObservation] | None = None,
    files_seen: int = 0,
) -> ScanObservation:
    return ScanObservation(
        source_id, run_id, audio or {}, directories or set(), artifacts or {}, files_seen
    )


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    with database.transaction():
        SourceRepository(database).upsert(
            "source", Path("/music"), set_eligible=True, analyze=True, enabled=True
        )
        SourceRepository(database).upsert(
            "other", Path("/other"), set_eligible=True, analyze=True, enabled=True
        )
    return database


def scan(lifecycle: ScanLifecycle, source_id: str, **kwargs: object) -> int:
    run_id = lifecycle.begin(source_id)
    lifecycle.observe(run_id, observation(source_id, run_id, **kwargs))
    lifecycle.succeed(run_id)
    return run_id


def test_failed_scan_does_not_reconcile_or_advance_last_successful(database: Database) -> None:
    lifecycle = ScanLifecycle(database)
    successful = scan(
        lifecycle,
        "source",
        audio={"A.flac": AudioObservation(1, 1), "B.flac": AudioObservation(2, 2)},
        files_seen=2,
    )
    failed = lifecycle.begin("source")
    lifecycle.observe(
        failed, observation("source", failed, audio={"A.flac": AudioObservation(1, 1)})
    )
    lifecycle.fail(failed, "traversal", "disk disconnected")

    assert (
        database.scalar("SELECT presence_status FROM tracks WHERE relative_path = 'B.flac'")
        == "present"
    )
    assert (
        database.scalar(
            "SELECT last_successful_scan_id FROM library_sources WHERE source_id = 'source'"
        )
        == successful
    )
    assert database.scalar("SELECT status FROM scan_runs WHERE id = ?", (failed,)) == "failed"


def test_success_missing_then_restore_reuses_track_identity_and_records_events(
    database: Database,
) -> None:
    lifecycle = ScanLifecycle(database)
    scan(lifecycle, "source", audio={"A.flac": AudioObservation(1, 1)})
    track_id = database.scalar("SELECT id FROM tracks WHERE relative_path = 'A.flac'")
    scan(lifecycle, "source")
    assert (
        database.scalar("SELECT presence_status FROM tracks WHERE id = ?", (track_id,)) == "missing"
    )
    scan(lifecycle, "source", audio={"A.flac": AudioObservation(1, 1)})

    assert database.scalar("SELECT id FROM tracks WHERE relative_path = 'A.flac'") == track_id
    assert (
        database.scalar("SELECT presence_status FROM tracks WHERE id = ?", (track_id,)) == "present"
    )
    assert database.execute(
        "SELECT event_type FROM track_events WHERE track_id = ? ORDER BY id", (track_id,)
    ).fetchall() == [
        ("discovered",),
        ("missing",),
        ("restored",),
    ]


def test_changed_filesystem_metadata_updates_track_and_records_event(database: Database) -> None:
    lifecycle = ScanLifecycle(database)
    scan(lifecycle, "source", audio={"A.flac": AudioObservation(1, 1)})
    scan(lifecycle, "source", audio={"A.flac": AudioObservation(2, 3)})

    assert database.execute(
        "SELECT size_bytes, mtime_ns FROM tracks WHERE relative_path = 'A.flac'"
    ).fetchone() == (2, 3)
    assert database.execute("SELECT event_type FROM track_events ORDER BY id").fetchall() == [
        ("discovered",),
        ("filesystem_metadata_changed",),
    ]


def test_reconciles_tracks_directories_and_artifacts_and_copies_counters(
    database: Database,
) -> None:
    lifecycle = ScanLifecycle(database)
    scan(
        lifecycle,
        "source",
        audio={"A.flac": AudioObservation(1, 1)},
        directories={"Techno"},
        artifacts={"_Serato_/crate": ArtifactObservation("serato_crate", 4, 5)},
        files_seen=7,
    )
    run_id = scan(lifecycle, "source", files_seen=0)

    assert database.execute(
        "SELECT files_seen, audio_seen, artifacts_seen FROM scan_runs WHERE id = ?", (run_id,)
    ).fetchone() == (0, 0, 0)
    for table in ("tracks", "directories", "library_artifacts"):
        assert database.scalar(f"SELECT presence_status FROM {table}") == "missing"


def test_observe_rejects_source_mismatch_and_terminal_runs(database: Database) -> None:
    lifecycle = ScanLifecycle(database)
    run_id = lifecycle.begin("source")
    with pytest.raises(ValueError, match="source"):
        lifecycle.observe(run_id, observation("other", run_id))
    lifecycle.observe(run_id, observation("source", run_id))
    lifecycle.succeed(run_id)
    with pytest.raises(ValueError, match="running"):
        lifecycle.succeed(run_id)
    with pytest.raises(ValueError, match="running"):
        lifecycle.observe(run_id, observation("source", run_id))


def test_succeed_rolls_back_every_mutation_when_final_update_fails(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    lifecycle = ScanLifecycle(database)
    previous = scan(lifecycle, "source", audio={"A.flac": AudioObservation(1, 1)})
    run_id = lifecycle.begin("source")
    lifecycle.observe(run_id, observation("source", run_id))
    original_execute = database.execute

    def fail_mark_succeeded(query: str, parameters: object = ()) -> sqlite3.Cursor:
        if "UPDATE scan_runs" in query and "succeeded" in query:
            raise RuntimeError("forced finalization failure")
        return original_execute(query, parameters)  # type: ignore[arg-type]

    monkeypatch.setattr(database, "execute", fail_mark_succeeded)
    with pytest.raises(RuntimeError, match="forced"):
        lifecycle.succeed(run_id)

    assert (
        database.scalar("SELECT presence_status FROM tracks WHERE relative_path = 'A.flac'")
        == "present"
    )
    assert database.scalar("SELECT status FROM scan_runs WHERE id = ?", (run_id,)) == "running"
    assert (
        database.scalar(
            "SELECT last_successful_scan_id FROM library_sources WHERE source_id = 'source'"
        )
        == previous
    )


def test_observe_rolls_back_partial_mutations_before_fail(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    lifecycle = ScanLifecycle(database)
    run_id = lifecycle.begin("source")
    original_execute = database.execute

    def fail_directory_insert(query: str, parameters: object = ()) -> sqlite3.Cursor:
        if "INSERT INTO directories" in query:
            raise RuntimeError("forced directory failure")
        return original_execute(query, parameters)  # type: ignore[arg-type]

    monkeypatch.setattr(database, "execute", fail_directory_insert)
    with pytest.raises(RuntimeError, match="forced"):
        lifecycle.observe(
            run_id,
            observation(
                "source",
                run_id,
                audio={"A.flac": AudioObservation(1, 1)},
                directories={"Techno"},
                artifacts={"_Serato_/crate": ArtifactObservation("serato_crate", 1, 1)},
                files_seen=2,
            ),
        )
    lifecycle.fail(run_id, "persist", "forced directory failure")

    assert database.scalar("SELECT COUNT(*) FROM tracks") == 0
    assert database.scalar("SELECT COUNT(*) FROM directories") == 0
    assert database.scalar("SELECT COUNT(*) FROM library_artifacts") == 0
    assert database.execute(
        "SELECT files_seen, audio_seen, artifacts_seen FROM scan_runs WHERE id = ?", (run_id,)
    ).fetchone() == (0, 0, 0)


def test_restoring_directory_and_artifact_reuses_their_identity(database: Database) -> None:
    lifecycle = ScanLifecycle(database)
    scan(
        lifecycle,
        "source",
        directories={"Techno"},
        artifacts={"_Serato_/crate": ArtifactObservation("serato_crate", 1, 1)},
    )
    directory_id = database.scalar("SELECT id FROM directories")
    artifact_id = database.scalar("SELECT id FROM library_artifacts")
    scan(lifecycle, "source")
    scan(
        lifecycle,
        "source",
        directories={"Techno"},
        artifacts={"_Serato_/crate": ArtifactObservation("serato_crate", 2, 3)},
    )

    assert database.execute("SELECT id, presence_status FROM directories").fetchone() == (
        directory_id,
        "present",
    )
    assert database.execute(
        "SELECT id, presence_status, size_bytes, mtime_ns FROM library_artifacts"
    ).fetchone() == (
        artifact_id,
        "present",
        2,
        3,
    )


def test_restored_track_with_changed_metadata_records_both_meaningful_events(
    database: Database,
) -> None:
    lifecycle = ScanLifecycle(database)
    scan(lifecycle, "source", audio={"A.flac": AudioObservation(1, 1)})
    scan(lifecycle, "source")
    scan(lifecycle, "source", audio={"A.flac": AudioObservation(2, 3)})

    assert database.execute("SELECT size_bytes, mtime_ns FROM tracks").fetchone() == (2, 3)
    assert database.execute("SELECT event_type FROM track_events ORDER BY id").fetchall() == [
        ("discovered",),
        ("missing",),
        ("restored",),
        ("filesystem_metadata_changed",),
    ]


def test_missing_since_does_not_change_after_a_track_is_already_missing(database: Database) -> None:
    lifecycle = ScanLifecycle(database)
    scan(lifecycle, "source", audio={"A.flac": AudioObservation(1, 1)})
    scan(lifecycle, "source")
    missing_since = database.scalar("SELECT missing_since FROM tracks")
    scan(lifecycle, "source")

    assert database.scalar("SELECT missing_since FROM tracks") == missing_since


def test_source_allows_only_one_running_scan_while_other_sources_are_independent(
    database: Database,
) -> None:
    lifecycle = ScanLifecycle(database)
    first = lifecycle.begin("source")

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        lifecycle.begin("source")
    lifecycle.observe(first, observation("source", first, audio={"A.flac": AudioObservation(1, 1)}))
    lifecycle.succeed(first)
    other = lifecycle.begin("other")
    resumed = lifecycle.begin("source")

    assert other != first
    assert resumed != first
