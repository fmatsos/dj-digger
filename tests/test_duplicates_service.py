from pathlib import Path
from threading import Event, Lock

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository
from dj_digger.duplicates.fingerprint import (
    FINGERPRINT_VERSION,
    Fingerprint,
    FingerprintExtractionError,
)
from dj_digger.duplicates.service import DuplicateService


class FakeExtractor:
    def __init__(self, fingerprints: dict[str, str], failures: set[str] | None = None) -> None:
        self._fingerprints = fingerprints
        self._failures = failures or set()
        self.calls: list[tuple[Path, float]] = []

    def extract(self, path: Path, *, timeout: float) -> Fingerprint:
        self.calls.append((path, timeout))
        if path.name in self._failures:
            raise FingerprintExtractionError(f"boom: {path.name}")
        fingerprint = self._fingerprints[path.name]
        import hashlib

        return Fingerprint(
            fingerprint=fingerprint,
            fingerprint_hash=hashlib.sha256(fingerprint.encode()).hexdigest(),
            fingerprint_version=FINGERPRINT_VERSION,
        )


def _track(
    database: Database, source_id: str, path: str, *, size_bytes: int = 10, mtime_ns: int = 20
) -> Track:
    if database.scalar(
        "SELECT 1 FROM library_sources WHERE source_id = ?", (source_id,)
    ) is None:
        with database.transaction():
            SourceRepository(database).upsert(
                source_id, Path(f"/{source_id}"), set_eligible=True, analyze=True, enabled=True
            )
    scan_id = database.scalar("SELECT id FROM scan_runs WHERE source_id = ?", (source_id,))
    if scan_id is None:
        scan_id = ScanRunRepository(database).start(source_id, scanner_version="test")
    with database.transaction():
        return TrackRepository(database).insert(
            source_id=source_id,
            relative_path=path,
            filename=Path(path).name,
            extension=Path(path).suffix,
            size_bytes=size_bytes,
            mtime_ns=mtime_ns,
            scan_id=int(scan_id),
        )


def _service(database: Database, extractor: FakeExtractor) -> DuplicateService:
    return DuplicateService(
        database, {"one": Path("/one"), "two": Path("/two")}, extractor=extractor  # type: ignore[arg-type]
    )


def test_analyze_empty_catalog_returns_zero_counts(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()

    result = _service(database, FakeExtractor({})).analyze()

    assert (result.files_total, result.analyzed, result.reused, result.failed) == (0, 0, 0, 0)
    assert (result.duplicate_files, result.duplicate_groups) == (0, 0)


def test_analyze_groups_identical_fingerprints_across_sources(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "A.flac")
    _track(database, "two", "A.mp3")
    extractor = FakeExtractor({"A.flac": "same", "A.mp3": "same"})

    result = _service(database, extractor).analyze()

    assert (result.analyzed, result.duplicate_files, result.duplicate_groups) == (2, 2, 1)


def test_analyze_with_source_excludes_other_sources_from_grouping(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "A.flac")
    _track(database, "two", "A.mp3")
    extractor = FakeExtractor({"A.flac": "same", "A.mp3": "same"})

    result = _service(database, extractor).analyze(source_id="one")

    assert result.analyzed == 1
    assert (result.duplicate_files, result.duplicate_groups) == (0, 0)


def test_analyze_reuses_fingerprint_matching_current_input_identity(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "A.flac", size_bytes=10, mtime_ns=20)
    extractor = FakeExtractor({"A.flac": "hash-a"})

    first = _service(database, extractor).analyze()
    second = _service(database, extractor).analyze()

    assert (first.analyzed, first.reused) == (1, 0)
    assert (second.analyzed, second.reused) == (0, 1)
    assert len(extractor.calls) == 1


def test_analyze_reextracts_when_input_identity_changes(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    track = _track(database, "one", "A.flac", size_bytes=10, mtime_ns=20)
    extractor = FakeExtractor({"A.flac": "hash-a"})
    _service(database, extractor).analyze()

    with database.transaction():
        database.execute(
            "UPDATE tracks SET mtime_ns = 99 WHERE id = ?", (track.id,)
        )

    result = _service(database, extractor).analyze()

    assert (result.analyzed, result.reused) == (1, 0)
    assert len(extractor.calls) == 2


def test_analyze_continues_after_a_per_track_failure_and_persists_successes(
    tmp_path: Path,
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "A.flac")
    _track(database, "one", "B.flac")
    extractor = FakeExtractor({"A.flac": "hash-a", "B.flac": "hash-b"}, failures={"B.flac"})

    result = _service(database, extractor).analyze()

    assert (result.analyzed, result.failed) == (1, 1)
    assert database.scalar("SELECT COUNT(*) FROM audio_fingerprints") == 1


def test_groups_return_deterministic_order(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "Z.flac")
    _track(database, "one", "A.flac")
    _track(database, "one", "M.flac")
    extractor = FakeExtractor(
        {"Z.flac": "hash-1", "A.flac": "hash-1", "M.flac": "hash-2"}
    )

    service = _service(database, extractor)
    service.analyze()
    _track(database, "one", "N.flac")
    extractor._fingerprints["N.flac"] = "hash-2"
    service.analyze()

    groups = service.groups()
    assert [group.fingerprint_hash for group in groups] == sorted(
        group.fingerprint_hash for group in groups
    )
    first_group = next(
        g
        for g in groups
        if len(g.members) == 2 and g.members[0].track.relative_path == "A.flac"
    )
    assert [m.track.relative_path for m in first_group.members] == ["A.flac", "Z.flac"]


def test_analyze_never_runs_more_extractions_than_workers(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    for index in range(4):
        _track(database, "one", f"{index}.flac")
    lock = Lock()
    both_started = Event()
    active = 0
    peak_active = 0

    class BoundedExtractor:
        def extract(self, path: Path, *, timeout: float) -> Fingerprint:
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
                if active == 2:
                    both_started.set()
            if not both_started.wait(timeout=2):
                raise TimeoutError("two extraction workers did not become active")
            with lock:
                active -= 1
            return Fingerprint(path.name, path.name, FINGERPRINT_VERSION)

    result = DuplicateService(
        database, {"one": Path("/one")}, extractor=BoundedExtractor()  # type: ignore[arg-type]
    ).analyze(workers=2)

    assert peak_active == 2
    assert result.analyzed == 4


def test_analyze_propagates_track_timeout_to_the_extractor(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "A.flac")
    extractor = FakeExtractor({"A.flac": "hash-a"})

    _service(database, extractor).analyze(track_timeout=42.0)

    assert extractor.calls[0][1] == 42.0


def test_analyze_rejects_non_positive_workers_and_timeout(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    service = _service(database, FakeExtractor({}))

    with pytest.raises(ValueError, match="workers must be positive"):
        service.analyze(workers=0)
    with pytest.raises(ValueError, match="track timeout must be positive"):
        service.analyze(track_timeout=0)


def test_concurrent_analyze_fails_without_holding_a_second_lock(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.sqlite"
    active_database = Database.open(catalog_path)
    active_database.migrate()
    competing_database = Database.open(catalog_path)

    with active_database.advisory_lock("duplicates"):
        with pytest.raises(RuntimeError, match="already held"):
            _service(competing_database, FakeExtractor({})).analyze()
