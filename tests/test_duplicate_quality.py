from pathlib import Path

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import (
    ScanRunRepository,
    SourceRepository,
    TechnicalAudioMetadataRepository,
    TrackRepository,
)
from dj_digger.duplicates.fingerprint import FINGERPRINT_VERSION, Fingerprint
from dj_digger.duplicates.quality import QualitySelector
from dj_digger.duplicates.repository import DuplicateRepository


def _track(
    database: Database, source_id: str, path: str, *, size_bytes: int = 10, mtime_ns: int = 20
) -> Track:
    if database.scalar("SELECT 1 FROM library_sources WHERE source_id = ?", (source_id,)) is None:
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


def _fingerprint(database: Database, track: Track, fingerprint_hash: str) -> None:
    with database.transaction():
        DuplicateRepository(database).upsert_fingerprint(
            track,
            Fingerprint(
                fingerprint=fingerprint_hash,
                fingerprint_hash=fingerprint_hash,
                fingerprint_version=FINGERPRINT_VERSION,
            ),
        )


def _facts(
    database: Database,
    track: Track,
    *,
    lossless: bool | None,
    bit_depth: int | None = None,
    sample_rate: int | None = None,
    bitrate: int | None = None,
) -> None:
    from dj_digger.analysis.audio import TechnicalAudioMetadata

    with database.transaction():
        TechnicalAudioMetadataRepository(database).upsert_facts(
            track,
            TechnicalAudioMetadata(
                lossless=lossless, bit_depth=bit_depth, sample_rate=sample_rate, bitrate=bitrate
            ),
            "test/1",
        )


def test_lossless_wins_over_lossy(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    flac = _track(database, "one", "A.flac")
    mp3 = _track(database, "one", "A.mp3")
    _fingerprint(database, flac, "hash")
    _fingerprint(database, mp3, "hash")
    _facts(database, flac, lossless=True, bit_depth=16, sample_rate=44100)
    _facts(database, mp3, lossless=False, bitrate=320000, sample_rate=44100)

    result = QualitySelector(database).mark_best_quality()

    assert result.status == "succeeded"
    assert result.marked_best == 1
    selections = DuplicateRepository(database).quality_selections(None)
    assert selections[("one", "hash")] == flac.id


def test_known_beats_unknown(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    known = _track(database, "one", "A.mp3")
    unknown = _track(database, "one", "B.mp3")
    _fingerprint(database, known, "hash")
    _fingerprint(database, unknown, "hash")
    _facts(database, known, lossless=False, bitrate=320000, sample_rate=44100)
    _facts(database, unknown, lossless=None)

    result = QualitySelector(database).mark_best_quality()

    selections = DuplicateRepository(database).quality_selections(None)
    assert selections[("one", "hash")] == known.id
    assert result.marked_best == 1


def test_lossless_tier_prefers_higher_bit_depth_then_sample_rate(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    a = _track(database, "one", "A.flac")
    b = _track(database, "one", "B.flac")
    c = _track(database, "one", "C.flac")
    for track in (a, b, c):
        _fingerprint(database, track, "hash")
    _facts(database, a, lossless=True, bit_depth=16, sample_rate=96000)
    _facts(database, b, lossless=True, bit_depth=24, sample_rate=44100)
    _facts(database, c, lossless=True, bit_depth=24, sample_rate=96000)

    QualitySelector(database).mark_best_quality()

    selections = DuplicateRepository(database).quality_selections(None)
    assert selections[("one", "hash")] == c.id


def test_lossy_tier_prefers_higher_bitrate_then_sample_rate(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    a = _track(database, "one", "A.mp3")
    b = _track(database, "one", "B.mp3")
    for track in (a, b):
        _fingerprint(database, track, "hash")
    _facts(database, a, lossless=False, bitrate=192000, sample_rate=44100)
    _facts(database, b, lossless=False, bitrate=320000, sample_rate=44100)

    QualitySelector(database).mark_best_quality()

    selections = DuplicateRepository(database).quality_selections(None)
    assert selections[("one", "hash")] == b.id


def test_ties_break_on_relative_path_ascending(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    z = _track(database, "one", "Z.flac")
    a = _track(database, "one", "A.flac")
    for track in (z, a):
        _fingerprint(database, track, "hash")
    _facts(database, z, lossless=True, bit_depth=16, sample_rate=44100)
    _facts(database, a, lossless=True, bit_depth=16, sample_rate=44100)

    QualitySelector(database).mark_best_quality()

    selections = DuplicateRepository(database).quality_selections(None)
    assert selections[("one", "hash")] == a.id


def test_independent_winners_are_elected_per_source_in_a_cross_source_group(
    tmp_path: Path,
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    one_low = _track(database, "one", "low.mp3")
    one_high = _track(database, "one", "high.flac")
    two_only = _track(database, "two", "only.mp3")
    for track in (one_low, one_high, two_only):
        _fingerprint(database, track, "hash")
    _facts(database, one_low, lossless=False, bitrate=128000, sample_rate=44100)
    _facts(database, one_high, lossless=True, bit_depth=16, sample_rate=44100)
    _facts(database, two_only, lossless=False, bitrate=320000, sample_rate=44100)

    result = QualitySelector(database).mark_best_quality()

    selections = DuplicateRepository(database).quality_selections(None)
    assert selections[("one", "hash")] == one_high.id
    assert ("two", "hash") not in selections
    assert result.marked_best == 1


def test_refuses_to_mark_when_scope_is_incomplete(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    analyzed = _track(database, "one", "A.flac")
    unanalyzed = _track(database, "one", "B.flac")
    _fingerprint(database, analyzed, "hash")
    _facts(database, analyzed, lossless=True, bit_depth=16, sample_rate=44100)

    result = QualitySelector(database).mark_best_quality()

    assert result.status == "failed"
    assert result.incomplete_track_ids == (unanalyzed.id,)
    assert DuplicateRepository(database).quality_selections(None) == {}


def test_incomplete_scope_leaves_prior_selections_unchanged(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    a = _track(database, "one", "A.flac")
    b = _track(database, "one", "B.flac")
    _fingerprint(database, a, "hash")
    _fingerprint(database, b, "hash")
    _facts(database, a, lossless=True, bit_depth=16, sample_rate=44100)
    _facts(database, b, lossless=False, bitrate=320000, sample_rate=44100)
    QualitySelector(database).mark_best_quality()
    before = DuplicateRepository(database).quality_selections(None)

    _track(database, "one", "C.flac")  # unanalyzed track breaks completeness
    result = QualitySelector(database).mark_best_quality()

    assert result.status == "failed"
    assert DuplicateRepository(database).quality_selections(None) == before
