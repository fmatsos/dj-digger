import csv
import os
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import SourceRepository
from dj_digger.exports.audit import AuditExporter


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    for source_id in ("music", "djing"):
        SourceRepository(database).upsert(
            source_id, tmp_path / source_id, set_eligible=True, analyze=True, enabled=True
        )
        database.execute(
            "INSERT INTO scan_runs (source_id, started_at, status, scanner_version) "
            "VALUES (?, 'now', 'succeeded', 't')",
            (source_id,),
        )
    return database


def _run(database: Database, source_id: str) -> int:
    return int(database.scalar("SELECT id FROM scan_runs WHERE source_id = ?", (source_id,)))


def _track(database: Database, source_id: str, path: str, *, present: str = "present") -> int:
    cursor = database.execute(
        "INSERT INTO tracks (source_id, relative_path, filename, extension, size_bytes, mtime_ns, "
        "presence_status, discovered_at, last_seen_at, created_scan_id, last_seen_scan_id) "
        "VALUES (?, ?, ?, ?, 42, 1700000000123456789, ?, 'now', 'now', ?, ?)",
        (
            source_id,
            path,
            Path(path).name,
            Path(path).suffix.upper(),
            present,
            _run(database, source_id),
            _run(database, source_id),
        ),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _directory(database: Database, source_id: str, path: str) -> None:
    database.execute(
        """
        INSERT INTO directories (
            source_id, relative_path, presence_status, discovered_at, last_seen_at,
            last_seen_scan_id
        ) VALUES (?, ?, 'present', 'now', 'now', ?)
        """,
        (source_id, path, _run(database, source_id)),
    )


def _artifact(
    database: Database, source_id: str, path: str, kind: str, *, present: str = "present"
) -> None:
    database.execute(
        """
        INSERT INTO library_artifacts (
            source_id, relative_path, artifact_type, size_bytes, mtime_ns,
            presence_status, first_seen_at, last_seen_at, last_seen_scan_id
        ) VALUES (
            ?, ?, ?, 9, 1700000000123456789, ?,
            '2020-01-01T00:00:00+00:00', '2020-01-02T00:00:00+00:00', ?
        )
        """,
        (source_id, path, kind, present, _run(database, source_id)),
    )


def test_files_and_metadata_use_present_catalog_rows_and_current_roots(
    database: Database, tmp_path: Path
) -> None:
    track_id = _track(database, "music", "Z/Name.FLAC")
    _track(database, "music", "gone.mp3", present="missing")
    database.execute(
        """
        INSERT INTO embedded_metadata (
            track_id, title, comment, metadata_extracted_at, extractor_version
        ) VALUES (?, ?, ?, 'now', 't')
        """,
        (track_id, "T", "a\nb"),
    )
    database.execute(
        """
        INSERT INTO technical_audio_metadata (
            track_id, duration_seconds, sample_rate, bitrate, probe_version, probed_at
        ) VALUES (?, 12.5, 44100, 320, 'ffmpeg', 'now')
        """,
        (track_id,),
    )
    SourceRepository(database).update_root("music", tmp_path / "moved")
    database.commit()

    AuditExporter(database).export(tmp_path / "out")
    files = list(
        csv.DictReader((tmp_path / "out/music-files.tsv").open(encoding="utf-8"), delimiter="\t")
    )
    metadata = list(
        csv.DictReader((tmp_path / "out/music-metadata.csv").open(encoding="utf-8", newline=""))
    )
    assert list(files[0]) == ["path", "filename", "extension", "size_bytes", "mtime"]
    assert files[0]["path"] == "Z/Name.FLAC" and files[0]["extension"] == ".flac"
    assert metadata[0]["SourceFile"] == "Z/Name.FLAC" and metadata[0]["Comment"] == "a\nb"
    assert metadata[0]["Duration"] == "12.5" and metadata[0]["AudioBitrate"] == "320"


def test_directory_facets_are_catalog_only_and_include_empty_directories(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _track(database, "music", "A/B/song.mp3")
    _directory(database, "music", "Empty")
    _directory(database, "music", "A/B")
    database.commit()
    monkeypatch.setattr(
        Path, "rglob", lambda *_: (_ for _ in ()).throw(AssertionError("filesystem"))
    )
    monkeypatch.setattr(os, "walk", lambda *_: (_ for _ in ()).throw(AssertionError("filesystem")))

    AuditExporter(database).export(tmp_path / "out")
    assert (tmp_path / "out/music-directories.txt").read_text() == "A/B\nEmpty\n"
    assert (tmp_path / "out/music-tree-depth-3.txt").read_text() == "A/B\nEmpty\n"
    assert (
        tmp_path / "out/music-directory-stats.tsv"
    ).read_text() == "level\tpath\ttracks\n1\tA\t1\n2\tA/B\t1\n"
    assert "\n.mp3\t1\n" in (tmp_path / "out/music-summary.txt").read_text()


def test_artifact_facets_validate_filter_and_derive_serato_path(
    database: Database, tmp_path: Path
) -> None:
    _artifact(database, "djing", "Traktor/collection.nml", "traktor_nml")
    _artifact(database, "djing", "gone.tsi", "traktor_tsi", present="missing")
    _directory(database, "djing", "_Serato_")
    database.commit()

    AuditExporter(database).export(tmp_path / "out")
    canonical = list(
        csv.DictReader(
            (tmp_path / "out/library-artifacts.tsv").open(encoding="utf-8"), delimiter="\t"
        )
    )
    assert list(canonical[0]) == [
        "source_id",
        "path",
        "absolute_path",
        "artifact_type",
        "size_bytes",
        "mtime",
        "present",
        "first_seen_at",
        "last_seen_at",
        "missing_since",
    ]
    assert canonical[0]["absolute_path"] == str(tmp_path / "djing/Traktor/collection.nml")
    assert (tmp_path / "out/traktor-files.tsv").read_text().count("collection.nml") == 1
    assert (tmp_path / "out/serato-directories.txt").read_text() == str(
        tmp_path / "djing/_Serato_"
    ) + "\n"
    assert "- library-artifacts.tsv\n" in (tmp_path / "out/README.txt").read_text()


def test_compatibility_false_publishes_only_canonical_without_touching_legacy(
    database: Database, tmp_path: Path
) -> None:
    _artifact(database, "music", "a.xml", "xml")
    database.commit()
    destination = tmp_path / "out"
    destination.mkdir()
    old = destination / "music-files.tsv"
    old.write_text("old\n")
    facets = AuditExporter(database).export(destination, legacy_compatibility=False)
    assert [facet.path.name for facet in facets] == ["library-artifacts.tsv"]
    assert old.read_text() == "old\n"


def test_legacy_source_id_cannot_escape_destination(database: Database, tmp_path: Path) -> None:
    SourceRepository(database).upsert(
        "../escape", tmp_path / "unsafe", set_eligible=True, analyze=True, enabled=True
    )

    with pytest.raises(ValueError, match="safe filename"):
        AuditExporter(database).export(tmp_path / "out")

    assert not (tmp_path / "escape-files.tsv").exists()
