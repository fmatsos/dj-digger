import csv
import json
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import SourceRepository
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
    database.commit()

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
