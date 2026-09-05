import sqlite3
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.curation import CandidateRef, CurationCatalog, CurationCatalogError, SearchFilters


def _catalog(path: Path) -> None:
    with Database.open(path) as database:
        database.migrate()
        database.execute(
            "INSERT INTO library_sources VALUES (?, ?, 1, 1, 1, ?, ?, NULL)",
            ("source-a", "/private/root", "2026-01-01", "2026-01-01"),
        )
        database.execute(
            "INSERT INTO scan_runs (id, source_id, started_at, status, scanner_version) "
            "VALUES (1, 'source-a', '2026-01-01', 'succeeded', 'test')"
        )
        database.execute(
            "INSERT INTO tracks (id, source_id, relative_path, filename, extension, size_bytes, "
            "mtime_ns, presence_status, discovered_at, last_seen_at, created_scan_id, "
            "last_seen_scan_id) "
            "VALUES (1, 'source-a', 'music/a.mp3', 'a.mp3', '.mp3', 10, 20, 'present', "
            "'2026-01-01', '2026-01-01', 1, 1)"
        )
        database.execute(
            "INSERT INTO embedded_metadata (track_id, title, artist, genre, metadata_extracted_at, "
            "extractor_version) "
            "VALUES (1, 'Track A', 'Artist A', 'Genre A', '2026-01-01', 'test')"
        )
        database.commit()


def test_overview_exposes_bounded_v1_data(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    _catalog(path)

    overview = CurationCatalog(path).overview()

    assert overview.contract_version == "curation/v1"
    assert overview.catalog_version == 9
    assert overview.available_tracks == 1
    assert overview.candidates == 1
    assert overview.latest_analysis.status is None
    assert overview.sources[0].source_id == "source-a"
    assert not hasattr(overview.sources[0], "root_path")

    forbidden = {
        "root_path",
        "absolute_path",
        "size_bytes",
        "mtime",
        "mtime_ns",
        "config_hash",
        "analyzer_version",
        "payload_json",
        "error",
        "sql",
    }
    assert not forbidden.intersection(_keys(overview.model_dump()))


def test_version_gate_and_missing_catalog_are_sanitized(tmp_path: Path) -> None:
    with pytest.raises(CurationCatalogError, match="unavailable"):
        CurationCatalog(tmp_path / "missing" / "catalog.sqlite").overview()
    assert not (tmp_path / "missing").exists()

    path = tmp_path / "catalog.sqlite"
    sqlite3.connect(path).close()
    with pytest.raises(CurationCatalogError, match="unsupported"):
        CurationCatalog(path).overview()


def test_search_and_details_return_relative_identity(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    _catalog(path)
    catalog = CurationCatalog(path)

    page = catalog.search(SearchFilters(query="Track A"), limit=1)
    assert len(page.candidates) == 1
    assert page.candidates[0].identity.path == "music/a.mp3"
    details = catalog.get_candidates([CandidateRef(source_id="source-a", track_id=1)])
    assert details.candidates[0].discovery.title == "Track A"


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _keys(child)}
    return set()
