from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository

HASH = "a" * 64


@pytest.fixture
def database(tmp_path: Path) -> Database:
    catalog = Database.open(tmp_path / "catalog.sqlite")
    catalog.migrate()
    return catalog


@pytest.fixture
def catalog(database: Database) -> TrackRepository:
    return TrackRepository(database)


@pytest.fixture
def identity():
    from dj_digger.analysis.config import AnalysisIdentity

    return AnalysisIdentity(schema_version=2, analyzer_version="1.0.0", config_hash=HASH)


@pytest.fixture
def eligibility(catalog: TrackRepository):
    from dj_digger.analysis.eligibility import AnalysisEligibility

    return AnalysisEligibility(catalog)


def present_track(
    database: Database,
    catalog: TrackRepository,
    *,
    source_id: str = "source",
    path: str = "Techno/A.flac",
    size: int = 10,
    mtime_ns: int = 20,
    analyze: bool = True,
    enabled: bool = True,
) -> Track:
    with database.transaction():
        SourceRepository(database).upsert(
            source_id,
            Path(f"/mnt/{source_id}"),
            set_eligible=True,
            analyze=analyze,
            enabled=enabled,
        )
    scan_id = ScanRunRepository(database).start(source_id, scanner_version="test")
    with database.transaction():
        track = catalog.insert(
            source_id=source_id,
            relative_path=path,
            filename=Path(path).name,
            extension=Path(path).suffix,
            size_bytes=size,
            mtime_ns=mtime_ns,
            scan_id=scan_id,
        )
        database.execute("UPDATE scan_runs SET status = 'succeeded' WHERE id = ?", (scan_id,))
    return track


def analysis(
    database: Database, track: Track, *, size: int, mtime_ns: int, status: str = "succeeded"
) -> None:
    run = database.execute(
        """
        INSERT INTO analysis_runs (
            started_at, status, analysis_schema_version, analyzer_version, config_hash
        ) VALUES ('now', 'succeeded', 2, '1.0.0', ?)
        """,
        (HASH,),
    )
    database.execute(
        """
        INSERT INTO audio_analysis (
            track_id, analysis_run_id, analysis_schema_version, analyzer_version, config_hash,
            input_size_bytes, input_mtime_ns, analysis_status, payload_json, created_at
        ) VALUES (?, ?, 2, '1.0.0', ?, ?, ?, ?, '{}', 'now')
        """,
        (track.id, run.lastrowid, HASH, size, mtime_ns, status),
    )
    database.commit()


def test_pending_excludes_exact_reusable_analysis(
    database: Database, catalog: TrackRepository, eligibility, identity
) -> None:
    track = present_track(database, catalog)
    analysis(database, track, size=10, mtime_ns=20)

    assert eligibility.pending(identity) == []


def test_pending_includes_track_when_current_facts_changed(
    database: Database, catalog: TrackRepository, eligibility, identity
) -> None:
    track = present_track(database, catalog, size=11, mtime_ns=21)
    analysis(database, track, size=10, mtime_ns=20)

    assert eligibility.pending(identity) == [track]


def test_missing_track_is_not_pending_but_analysis_remains(
    database: Database, catalog: TrackRepository, eligibility, identity
) -> None:
    track = present_track(database, catalog)
    analysis(database, track, size=10, mtime_ns=20)
    database.execute("UPDATE tracks SET presence_status = 'missing' WHERE id = ?", (track.id,))
    database.commit()

    assert eligibility.pending(identity) == []
    assert catalog.analysis_history(track.id)


def test_pending_includes_track_with_non_successful_matching_analysis(
    database: Database, catalog: TrackRepository, eligibility, identity
) -> None:
    track = present_track(database, catalog)
    analysis(database, track, size=10, mtime_ns=20, status="failed")

    assert eligibility.pending(identity) == [track]


@pytest.mark.parametrize("analyze,enabled", [(False, True), (True, False)])
def test_pending_excludes_non_analyzable_sources(
    database: Database,
    catalog: TrackRepository,
    eligibility,
    identity,
    analyze: bool,
    enabled: bool,
) -> None:
    present_track(database, catalog, analyze=analyze, enabled=enabled)

    assert eligibility.pending(identity) == []


def test_pending_filters_by_exact_source_and_safe_path_prefix(
    database: Database, catalog: TrackRepository, eligibility, identity
) -> None:
    matching = present_track(database, catalog, source_id="one", path="House/2026/A.flac")
    present_track(database, catalog, source_id="one", path="HouseX/B.flac")
    present_track(database, catalog, source_id="two", path="House/2026/C.flac")
    literal_percent = present_track(database, catalog, source_id="one", path="House%/D.flac")
    present_track(database, catalog, source_id="one", path="HouseA/E.flac")

    assert eligibility.pending(identity, source_id="one", path_prefix="House/2026") == [matching]
    assert eligibility.pending(identity, source_id="one", path_prefix="House%") == [literal_percent]
