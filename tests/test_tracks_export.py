import csv
import json
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from dj_digger.catalog.database import Database
from dj_digger.catalog.read_repositories import LibraryReadRepository
from dj_digger.catalog.repositories import SourceRepository, TrackRepository
from dj_digger.exports.tracks import TracksExporter

TRACK_INSERT = """
    INSERT INTO tracks (
        source_id, relative_path, filename, extension, size_bytes, mtime_ns,
        presence_status, discovered_at, last_seen_at, created_scan_id, last_seen_scan_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'now', 'now', ?, ?)
"""


def insert_track(
    database: Database,
    *,
    source_id: str,
    relative_path: str,
    mtime_ns: int,
    presence_status: str = "present",
) -> int:
    run_id = database.scalar("SELECT id FROM scan_runs WHERE source_id = ?", (source_id,))
    cursor = database.execute(
        TRACK_INSERT,
        (
            source_id,
            relative_path,
            Path(relative_path).name,
            Path(relative_path).suffix.upper(),
            12,
            mtime_ns,
            presence_status,
            run_id,
            run_id,
        ),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database.open(tmp_path / "catalog.sqlite")
    db.migrate()
    with db.transaction():
        SourceRepository(db).upsert(
            "src", tmp_path / "music", set_eligible=True, analyze=True, enabled=True
        )
        SourceRepository(db).upsert(
            "other", tmp_path / "other", set_eligible=False, analyze=True, enabled=True
        )
    db.execute(
        """
        INSERT INTO scan_runs (source_id, started_at, status, scanner_version)
        VALUES ('src', 'now', 'succeeded', 't')
        """
    )
    db.execute(
        """
        INSERT INTO scan_runs (source_id, started_at, status, scanner_version)
        VALUES ('other', 'now', 'succeeded', 't')
        """
    )
    track_id = insert_track(
        db,
        source_id="src",
        relative_path="Dir/Éxample.FLAC",
        mtime_ns=1_700_000_000_123_456_789,
    )
    insert_track(
        db,
        source_id="other",
        relative_path="Z.ogg",
        mtime_ns=1_700_000_000_000_000_000,
    )
    db.execute(
        """
        INSERT INTO embedded_metadata (
            track_id, title, comment, metadata_extracted_at, extractor_version
        ) VALUES (?, ?, ?, 'now', 't')
        """,
        (track_id, "Title", "line1\nline2"),
    )
    db.execute(
        """
        INSERT INTO technical_audio_metadata (
            track_id, duration_seconds, sample_rate, channels, codec, container,
            bitrate, lossless, probe_version, probed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (track_id, 1.5, 44100, 2, "flac", "flac", 900, 1, "t", "now"),
    )
    db.commit()
    return db


def test_export_header_and_present_joined_rows(database: Database, tmp_path: Path) -> None:
    schema = Path("schemas/tracks.schema.json")
    out = tmp_path / "tracks.tsv"
    columns = json.loads(schema.read_text())["x-tabular"]["columns"]
    with database.transaction():
        insert_track(
            database,
            source_id="src",
            relative_path="A\tB.mp3",
            mtime_ns=1_700_000_000_000_000_000,
        )
        insert_track(
            database,
            source_id="src",
            relative_path="zzz.wav",
            mtime_ns=1_700_000_000_000_000_000,
            presence_status="missing",
        )
        SourceRepository(database).update_root("src", tmp_path / "relocated")

    facet = TracksExporter(database, schema_path=schema).export(out)
    rows = list(csv.DictReader(out.open(newline="", encoding="utf-8"), delimiter="\t"))

    assert facet.row_count == 3
    assert list(rows[0]) == columns
    assert [row["path"] for row in rows] == ["Z.ogg", "A\tB.mp3", "Dir/Éxample.FLAC"]
    assert rows[2]["source_id"] == "src"
    assert rows[2]["absolute_path"] == str(tmp_path / "relocated" / "Dir/Éxample.FLAC")
    assert rows[2]["extension"] == ".flac" and rows[2]["mtime"] == datetime.fromtimestamp(
        1_700_000_000
    ).isoformat(timespec="seconds")
    assert rows[2]["comment"] == "line1\nline2"
    assert rows[2]["duration_seconds"] == "1.5"
    assert rows[2]["set_eligible"] == "true"
    assert rows[2]["lossless"] == "true"
    assert rows[0]["set_eligible"] == "false"
    assert rows[0]["title"] == ""
    assert rows[0]["lossless"] == ""


def test_track_repository_keeps_no_export_read_boundary() -> None:
    assert not hasattr(TrackRepository, "export_rows")


def _fingerprint(database: Database, track_id: int, fingerprint_hash: str) -> None:
    database.execute(
        """
        INSERT INTO audio_fingerprints (
            track_id, fingerprint, fingerprint_hash, fingerprint_version,
            input_size_bytes, input_mtime_ns, fingerprinted_at
        ) VALUES (?, ?, ?, 'test/1', 12, 1, 'now')
        """,
        (track_id, fingerprint_hash, fingerprint_hash),
    )


def test_export_reports_the_three_duplicate_quality_states(
    database: Database, tmp_path: Path
) -> None:
    with database.transaction():
        winner = insert_track(
            database, source_id="src", relative_path="Dup/Winner.flac", mtime_ns=1
        )
        loser = insert_track(
            database, source_id="src", relative_path="Dup/Loser.mp3", mtime_ns=1
        )
        unmarked_a = insert_track(
            database, source_id="src", relative_path="Unmarked/A.flac", mtime_ns=1
        )
        unmarked_b = insert_track(
            database, source_id="src", relative_path="Unmarked/B.mp3", mtime_ns=1
        )
        _fingerprint(database, winner, "marked-hash")
        _fingerprint(database, loser, "marked-hash")
        _fingerprint(database, unmarked_a, "unmarked-hash")
        _fingerprint(database, unmarked_b, "unmarked-hash")
        database.execute(
            """
            INSERT INTO duplicate_quality_selections (
                source_id, fingerprint_hash, preferred_track_id, ranking_version, selected_at
            ) VALUES ('src', 'marked-hash', ?, 'test/1', 'now')
            """,
            (winner,),
        )

    out = tmp_path / "tracks.tsv"
    TracksExporter(database).export(out)
    rows = {
        row["path"]: row
        for row in csv.DictReader(out.open(newline="", encoding="utf-8"), delimiter="\t")
    }

    assert rows["Dir/Éxample.FLAC"]["duplicate_group_id"] == ""
    assert rows["Dir/Éxample.FLAC"]["duplicate_best_quality"] == ""
    assert rows["Dup/Winner.flac"]["duplicate_group_id"] == "marked-hash"
    assert rows["Dup/Winner.flac"]["duplicate_best_quality"] == "true"
    assert rows["Dup/Loser.mp3"]["duplicate_group_id"] == "marked-hash"
    assert rows["Dup/Loser.mp3"]["duplicate_best_quality"] == "false"
    assert rows["Unmarked/A.flac"]["duplicate_group_id"] == "unmarked-hash"
    assert rows["Unmarked/A.flac"]["duplicate_best_quality"] == ""
    assert rows["Unmarked/B.mp3"]["duplicate_group_id"] == "unmarked-hash"
    assert rows["Unmarked/B.mp3"]["duplicate_best_quality"] == ""


def test_export_excludes_missing_members_from_duplicate_groups(
    database: Database, tmp_path: Path
) -> None:
    with database.transaction():
        present = insert_track(
            database, source_id="src", relative_path="Solo/Present.flac", mtime_ns=1
        )
        missing = insert_track(
            database,
            source_id="src",
            relative_path="Solo/Missing.mp3",
            mtime_ns=1,
            presence_status="missing",
        )
        _fingerprint(database, present, "solo-hash")
        _fingerprint(database, missing, "solo-hash")

    out = tmp_path / "tracks.tsv"
    TracksExporter(database).export(out)
    rows = {
        row["path"]: row
        for row in csv.DictReader(out.open(newline="", encoding="utf-8"), delimiter="\t")
    }

    assert "Solo/Missing.mp3" not in rows
    assert rows["Solo/Present.flac"]["duplicate_group_id"] == ""
    assert rows["Solo/Present.flac"]["duplicate_best_quality"] == ""


def test_export_scopes_quality_state_to_the_members_own_source(
    database: Database, tmp_path: Path
) -> None:
    with database.transaction():
        src_track = insert_track(
            database, source_id="src", relative_path="Cross/A.flac", mtime_ns=1
        )
        other_track = insert_track(
            database, source_id="other", relative_path="Cross/A.mp3", mtime_ns=1
        )
        _fingerprint(database, src_track, "cross-hash")
        _fingerprint(database, other_track, "cross-hash")
        database.execute(
            """
            INSERT INTO duplicate_quality_selections (
                source_id, fingerprint_hash, preferred_track_id, ranking_version, selected_at
            ) VALUES ('src', 'cross-hash', ?, 'test/1', 'now')
            """,
            (src_track,),
        )

    out = tmp_path / "tracks.tsv"
    TracksExporter(database).export(out)
    rows = {
        row["path"]: row
        for row in csv.DictReader(out.open(newline="", encoding="utf-8"), delimiter="\t")
    }

    assert rows["Cross/A.flac"]["duplicate_best_quality"] == "true"
    assert rows["Cross/A.mp3"]["duplicate_group_id"] == "cross-hash"
    assert rows["Cross/A.mp3"]["duplicate_best_quality"] == ""


def test_view_backed_export_is_byte_identical_to_legacy_projection(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_rows = database.execute(
        """
        SELECT t.id, t.source_id, t.relative_path, t.filename, t.extension,
               t.size_bytes, t.mtime_ns, s.set_eligible,
               e.title, e.artist, e.album_artist, e.album, e.track_number,
               e.disc_number, e.genre, e.date, e.year, e.composer, e.comment,
               e.tag_bpm, e.tag_initial_key, e.grouping,
               technical.duration_seconds, technical.sample_rate, technical.channels,
               technical.codec, technical.container, technical.bitrate, technical.lossless,
               dup.fingerprint_hash,
               CASE
                   WHEN dup.fingerprint_hash IS NULL THEN NULL
                   WHEN dqs.preferred_track_id IS NULL THEN NULL
                   WHEN dqs.preferred_track_id = t.id THEN 1
                   ELSE 0
               END
        FROM tracks AS t
        JOIN library_sources AS s ON s.source_id = t.source_id
        LEFT JOIN embedded_metadata AS e ON e.track_id = t.id
        LEFT JOIN technical_audio_metadata AS technical ON technical.track_id = t.id
        LEFT JOIN (
            SELECT af.track_id, af.fingerprint_hash
            FROM audio_fingerprints af
            JOIN tracks t2 ON t2.id = af.track_id
            JOIN library_sources s2 ON s2.source_id = t2.source_id
            WHERE t2.presence_status = 'present' AND s2.enabled = 1
              AND af.fingerprint_hash IN (
                  SELECT af2.fingerprint_hash
                  FROM audio_fingerprints af2
                  JOIN tracks t3 ON t3.id = af2.track_id
                  JOIN library_sources s3 ON s3.source_id = t3.source_id
                  WHERE t3.presence_status = 'present' AND s3.enabled = 1
                  GROUP BY af2.fingerprint_hash
                  HAVING COUNT(*) >= 2
              )
        ) dup ON dup.track_id = t.id
        LEFT JOIN duplicate_quality_selections dqs
            ON dqs.source_id = t.source_id AND dqs.fingerprint_hash = dup.fingerprint_hash
        WHERE t.presence_status = 'present'
        ORDER BY t.source_id, t.relative_path, t.id
        """
    ).fetchall()
    legacy_path = tmp_path / "legacy.tsv"
    view_path = tmp_path / "view.tsv"

    with monkeypatch.context() as patch:
        patch.setattr(LibraryReadRepository, "export_rows", lambda _repository: legacy_rows)
        TracksExporter(database).export(legacy_path)
    TracksExporter(database).export(view_path)

    assert view_path.read_bytes() == legacy_path.read_bytes()


def test_empty_catalog_header_only(database: Database, tmp_path: Path) -> None:
    database.execute("UPDATE tracks SET presence_status='missing'")
    database.commit()
    out = tmp_path / "empty.tsv"
    TracksExporter(database).export(out)
    assert len(out.read_text().splitlines()) == 1


def test_invalid_row_preserves_previous_destination(database: Database, tmp_path: Path) -> None:
    out = tmp_path / "tracks.tsv"
    TracksExporter(database).export(out)
    old = out.read_bytes()
    database.execute("UPDATE embedded_metadata SET tag_bpm=0")
    database.commit()
    with pytest.raises(ValidationError):
        TracksExporter(database).export(out)
    assert out.read_bytes() == old
    assert not list(tmp_path.glob(".tracks.tsv.*.tmp"))
