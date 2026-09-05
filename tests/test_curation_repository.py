import sqlite3
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.curation import CreateCurationDraft, CurationRepository, CurationTrack


def _catalog_with_tracks(path: Path) -> Database:
    database = Database.open(path)
    database.migrate()
    database.execute(
        "INSERT INTO library_sources VALUES (?, ?, 1, 1, 1, ?, ?, NULL)",
        ("fixture", "/fixture", "now", "now"),
    )
    database.execute(
        "INSERT INTO scan_runs (id, source_id, started_at, status, scanner_version) "
        "VALUES (1, 'fixture', 'now', 'succeeded', 'test')"
    )
    for track_id in (1, 2, 3):
        database.execute(
            """INSERT INTO tracks VALUES
            (?, 'fixture', ?, ?, '.flac', 1, 1, 'present',
             'now', 'now', NULL, NULL, 1, 1)""",
            (track_id, f"{track_id}.flac", f"{track_id}.flac"),
        )
    database.commit()
    return database


def _draft(
    *, creation_id: str = "stable-id", track_ids: tuple[int, ...] = (2, 1)
) -> CreateCurationDraft:
    return CreateCurationDraft(
        id=creation_id,
        name="Warm-up",
        kind="set",
        user_prompt="Build a gradual progression",
        report_markdown="# Selection\nReasoned ordering.",
        model_config_data={"provider": "local", "model": "curator-v1", "temperature": 0.2},
        tracks=tuple(
            CurationTrack(track_id=track_id, position=position)
            for position, track_id in enumerate(track_ids, start=1)
        ),
    )


def test_create_draft_persists_complete_ordered_creation(tmp_path: Path) -> None:
    database = _catalog_with_tracks(tmp_path / "catalog.sqlite")
    creation = CurationRepository(database).create_draft(_draft())

    assert creation.status == "draft"
    assert creation.validated_at is None
    assert creation.model_config_data["model"] == "curator-v1"
    assert creation.tracks == (
        CurationTrack(track_id=2, position=1),
        CurationTrack(track_id=1, position=2),
    )


def test_create_draft_rolls_back_parent_when_any_track_is_invalid(tmp_path: Path) -> None:
    database = _catalog_with_tracks(tmp_path / "catalog.sqlite")

    with pytest.raises(sqlite3.IntegrityError):
        CurationRepository(database).create_draft(_draft(track_ids=(1, 999)))

    assert database.scalar("SELECT count(*) FROM curation_creations") == 0
    assert database.scalar("SELECT count(*) FROM curation_creation_tracks") == 0


def test_creation_rejects_duplicate_positions_at_database_boundary(tmp_path: Path) -> None:
    database = _catalog_with_tracks(tmp_path / "catalog.sqlite")
    repository = CurationRepository(database)
    repository.create_draft(_draft())

    with pytest.raises(sqlite3.IntegrityError):
        database.execute("INSERT INTO curation_creation_tracks VALUES ('stable-id', 3, 1)")


def test_validate_is_idempotent_and_cannot_return_to_draft(tmp_path: Path) -> None:
    database = _catalog_with_tracks(tmp_path / "catalog.sqlite")
    repository = CurationRepository(database)
    repository.create_draft(_draft())

    first = repository.validate("stable-id")
    second = repository.validate("stable-id")

    assert first.status == second.status == "validated"
    assert first.validated_at == second.validated_at
    with pytest.raises(sqlite3.IntegrityError):
        database.execute("UPDATE curation_creations SET status = 'draft' WHERE id = 'stable-id'")


def test_begin_immediate_serializes_concurrent_curation_writers(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    first = _catalog_with_tracks(path)
    second = Database.open(path)
    second.execute("PRAGMA busy_timeout = 1")

    first.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            CurationRepository(second).create_draft(_draft(creation_id="blocked"))
    finally:
        first.execute("ROLLBACK")

    assert second.scalar("SELECT count(*) FROM curation_creations WHERE id = 'blocked'") == 0
