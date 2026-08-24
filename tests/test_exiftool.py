import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import (
    EmbeddedMetadataRepository,
    ScanRunRepository,
    SourceRepository,
    TrackRepository,
)
from dj_digger.metadata.exiftool import (
    EMBEDDED_FIELDS,
    EmbeddedMetadata,
    ExifToolExtractor,
    ExtractionError,
    MetadataService,
)


def track(relative_path: str = "Acid.flac") -> Track:
    return Track(
        id=1,
        source_id="source",
        relative_path=relative_path,
        filename=Path(relative_path).name,
        extension=".flac",
        size_bytes=1,
        mtime_ns=2,
        presence_status="present",
    )


def catalog_with_two_tracks(
    tmp_path: Path, *, one_track: bool = False
) -> tuple[Database, Track, Track]:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    SourceRepository(database).upsert(
        "source", tmp_path / "source", set_eligible=True, analyze=True, enabled=True
    )
    run_id = ScanRunRepository(database).start("source", scanner_version="test")
    tracks = TrackRepository(database)
    first = tracks.insert(
        source_id="source", relative_path="A.flac", filename="A.flac", extension=".flac",
        size_bytes=1, mtime_ns=2, scan_id=run_id,
    )
    second = first if one_track else tracks.insert(
        source_id="source", relative_path="B.flac", filename="B.flac", extension=".flac",
        size_bytes=3, mtime_ns=4, scan_id=run_id,
    )
    return database, first, second


def test_exiftool_normalizes_only_embedded_tag_fields() -> None:
    metadata = ExifToolExtractor().normalize(
        {
            "Title": "Acid",
            "Artist": "X",
            "BPM": "145.5",
            "Duration": 123.4,
        }
    )

    assert EMBEDDED_FIELDS == (
        "Title",
        "Artist",
        "AlbumArtist",
        "Album",
        "Track",
        "DiscNumber",
        "Genre",
        "Date",
        "Year",
        "Composer",
        "Comment",
        "BPM",
        "InitialKey",
        "Grouping",
    )
    assert metadata.title == "Acid"
    assert metadata.artist == "X"
    assert metadata.tag_bpm == 145.5
    assert not hasattr(metadata, "duration_seconds")

    malformed = ExifToolExtractor().normalize({"Title": ["not text"], "BPM": "not-a-number"})
    assert malformed.title is None
    assert malformed.tag_bpm is None


def test_exiftool_uses_argv_and_preserves_newline_paths(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **_kwargs: object) -> object:
        calls.append(argv)
        return type("Result", (), {"stdout": '[{"SourceFile":"odd\\nname.flac","Title":"Acid"}]'})()

    monkeypatch.setattr("dj_digger.metadata.exiftool.subprocess.run", run)
    metadata = ExifToolExtractor().extract(track("odd\nname.flac"))

    assert metadata.title == "Acid"
    assert calls == [
        [
            "exiftool",
            "-json",
            "-charset",
            "filename=UTF8",
            "-Title",
            "-Artist",
            "-AlbumArtist",
            "-Album",
            "-Track",
            "-DiscNumber",
            "-Genre",
            "-Date",
            "-Year",
            "-Composer",
            "-Comment",
            "-BPM#",
            "-InitialKey",
            "-Grouping",
            "odd\nname.flac",
        ]
    ]


def test_exiftool_batches_large_track_lists(monkeypatch) -> None:
    calls: list[list[str]] = []
    tracks = [replace(track(f"{letter}.flac"), id=index) for index, letter in enumerate("ABC", 1)]

    def run(argv: list[str], **_kwargs: object) -> object:
        calls.append(argv)
        files = [argument for argument in argv if argument.endswith(".flac")]
        payload = [{"SourceFile": path, "Title": path} for path in files]
        return type("Result", (), {"stdout": json.dumps(payload)})()

    monkeypatch.setattr("dj_digger.metadata.exiftool.subprocess.run", run)
    result = ExifToolExtractor(version="test", batch_size=2).extract_many(tracks)

    assert len(calls) == 2
    assert set(result.metadata) == {1, 2, 3}


def test_exiftool_matches_duplicate_paths_in_source_order(monkeypatch) -> None:
    first = track("A.flac")
    second = replace(first, id=2, source_id="other")

    def run(_argv: list[str], **_kwargs: object) -> object:
        return type(
            "Result",
            (),
            {
                "stdout": (
                    '[{"SourceFile":"A.flac","Title":"first"},'
                    '{"SourceFile":"A.flac","Title":"second"}]'
                )
            },
        )()

    monkeypatch.setattr("dj_digger.metadata.exiftool.subprocess.run", run)
    result = ExifToolExtractor(version="test", batch_size=2).extract_many([first, second])

    assert result.metadata[first.id].title == "first"
    assert result.metadata[second.id].title == "second"


def test_nonzero_exiftool_batch_keeps_success_and_reports_only_bad_track(
    tmp_path: Path, monkeypatch
) -> None:
    database, first, second = catalog_with_two_tracks(tmp_path)

    def run(argv: list[str], **_kwargs: object) -> object:
        if argv[-1] == "-ver":
            return type("Result", (), {"stdout": "12.99\n", "returncode": 0})()
        return type(
            "Result",
            (),
            {
                "stdout": (
                    '[{"SourceFile":"' + str(tmp_path / "source" / "A.flac")
                    + '","Title":"Acid"},{"SourceFile":"'
                    + str(tmp_path / "source" / "B.flac") + '","Error":"bad tag"}]'
                ),
                "returncode": 1,
            },
        )()

    monkeypatch.setattr("dj_digger.metadata.exiftool.subprocess.run", run)
    result = MetadataService(database, ExifToolExtractor()).refresh("source")

    assert result.extracted == 1
    assert result.failed == 1
    assert database.scalar(
        "SELECT title FROM embedded_metadata WHERE track_id = ?", (first.id,)
    ) == "Acid"
    assert database.scalar(
        "SELECT presence_status FROM tracks WHERE id = ?", (second.id,)
    ) == "present"
    assert database.execute("SELECT event_type FROM track_events ORDER BY id").fetchall() == [
        ("embedded_metadata_changed",),
        ("embedded_metadata_failed",),
    ]


def test_exiftool_reported_version_changes_refresh_eligibility(tmp_path: Path, monkeypatch) -> None:
    database, first, _second = catalog_with_two_tracks(tmp_path, one_track=True)
    versions = iter(("12.98\n", "12.99\n"))

    def run(argv: list[str], **_kwargs: object) -> object:
        if argv[-1] == "-ver":
            return type("Result", (), {"stdout": next(versions), "returncode": 0})()
        return type(
            "Result",
            (),
            {
                "stdout": (
                    '[{"SourceFile":"' + str(tmp_path / "source" / "A.flac")
                    + '","Title":"Acid"}]'
                ),
                "returncode": 0,
            },
        )()

    monkeypatch.setattr("dj_digger.metadata.exiftool.subprocess.run", run)
    assert MetadataService(database, ExifToolExtractor()).refresh("source").extracted == 1
    assert MetadataService(database, ExifToolExtractor()).refresh("source").extracted == 1
    assert database.scalar(
        "SELECT extractor_version FROM embedded_metadata WHERE track_id = ?", (first.id,)
    ) == "12.99"


def test_version_probe_failure_records_each_present_track_failure(tmp_path: Path) -> None:
    database, first, second = catalog_with_two_tracks(tmp_path)

    class BrokenExtractor:
        @property
        def version(self) -> str:
            raise ExtractionError("version unavailable")

    result = MetadataService(database, BrokenExtractor()).refresh("source")  # type: ignore[arg-type]

    assert result.failed == 2
    assert result.skipped == 0
    assert database.execute("SELECT event_type FROM track_events ORDER BY id").fetchall() == [
        ("embedded_metadata_failed",),
        ("embedded_metadata_failed",),
    ]
    assert database.execute(
        "SELECT id, presence_status FROM tracks WHERE id IN (?, ?) ORDER BY id",
        (first.id, second.id),
    ).fetchall() == [(first.id, "present"), (second.id, "present")]


def test_metadata_eligibility_honors_a_path_prefix(tmp_path: Path) -> None:
    database, first, _second = catalog_with_two_tracks(tmp_path)

    eligible = EmbeddedMetadataRepository(database).eligible_tracks(
        "source",
        extractor_version="test",
        normalization_version="1",
        force=True,
        path_prefix="A",
    )

    assert eligible == [first]


def test_global_extraction_failure_events_are_atomic(tmp_path: Path) -> None:
    database, _first, second = catalog_with_two_tracks(tmp_path)
    database.execute(
        f"""
        CREATE TRIGGER reject_second_metadata_failure
        BEFORE INSERT ON track_events
        WHEN NEW.track_id = {second.id}
        BEGIN
            SELECT RAISE(ABORT, 'reject second failure');
        END
        """
    )
    database.commit()

    class BrokenExtractor:
        version = "test"

        def extract_many(self, _tracks: list[Track]) -> dict[int, EmbeddedMetadata]:
            raise ExtractionError("batch unavailable")

    with pytest.raises(sqlite3.IntegrityError, match="reject second failure"):
        MetadataService(database, BrokenExtractor()).refresh("source")  # type: ignore[arg-type]

    assert database.scalar("SELECT COUNT(*) FROM track_events") == 0


def test_metadata_refresh_is_incremental_records_changes_and_keeps_failures_present(
    tmp_path: Path,
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    root = tmp_path / "source"
    SourceRepository(database).upsert(
        "source", root, set_eligible=True, analyze=True, enabled=True
    )
    run_id = ScanRunRepository(database).start("source", scanner_version="test")
    tracks = TrackRepository(database)
    first = tracks.insert(
        source_id="source", relative_path="A.flac", filename="A.flac", extension=".flac",
        size_bytes=1, mtime_ns=2, scan_id=run_id,
    )
    second = tracks.insert(
        source_id="source", relative_path="B.flac", filename="B.flac", extension=".flac",
        size_bytes=3, mtime_ns=4, scan_id=run_id,
    )

    class Extractor:
        version = "exiftool-test"

        def __init__(self) -> None:
            self.calls: list[list[int]] = []

        def extract_many(self, selected: list[Track]) -> dict[int, EmbeddedMetadata]:
            self.calls.append([item.id for item in selected])
            return {
                first.id: EmbeddedMetadata(title="Acid", tag_bpm=145.0),
            }

    extractor = Extractor()
    service = MetadataService(database, extractor)  # type: ignore[arg-type]

    first_run = service.refresh("source")
    second_run = service.refresh("source")

    assert first_run.extracted == 1
    assert first_run.failed == 1
    assert first_run.skipped == 0
    assert second_run.extracted == 0
    assert second_run.failed == 1
    assert second_run.skipped == 1
    assert extractor.calls == [[first.id, second.id], [second.id]]
    assert (
        database.scalar("SELECT presence_status FROM tracks WHERE id = ?", (second.id,))
        == "present"
    )
    assert database.execute(
        "SELECT event_type FROM track_events ORDER BY id"
    ).fetchall() == [
        ("embedded_metadata_changed",),
        ("embedded_metadata_failed",),
        ("embedded_metadata_failed",),
    ]

    database.execute("UPDATE tracks SET size_bytes = 5 WHERE id = ?", (first.id,))
    database.commit()
    changed = service.refresh("source")

    assert changed.extracted == 1
    assert database.execute(
        "SELECT payload_json FROM track_events WHERE event_type = 'embedded_metadata_changed' "
        "ORDER BY id"
    ).fetchall() == [
        ('{"changed_fields":["title","tag_bpm"]}',),
    ]

    forced = service.refresh("source", force=True)
    assert forced.extracted == 1
    assert forced.failed == 1
    assert extractor.calls[-1] == [first.id, second.id]
