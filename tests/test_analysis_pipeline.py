from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository

IDENTITY = AnalysisIdentity(schema_version=2, analyzer_version="test", config_hash="a" * 64)


def _track(database: Database, source_id: str, path: str) -> None:
    SourceRepository(database).upsert(
        source_id, Path(f"/{source_id}"), set_eligible=True, analyze=True, enabled=True
    )
    scan_id = database.scalar("SELECT id FROM scan_runs WHERE source_id = ?", (source_id,))
    if scan_id is None:
        scan_id = ScanRunRepository(database).start(source_id, scanner_version="test")
    TrackRepository(database).insert(
        source_id=source_id,
        relative_path=path,
        filename=Path(path).name,
        extension=Path(path).suffix,
        size_bytes=10,
        mtime_ns=20,
        scan_id=int(scan_id),
    )


def _pipeline(database: Database, calls: list[str]):
    from dj_digger.analysis.pipeline import AnalysisPipeline

    def extract(track: Any) -> Mapping[str, object]:
        calls.append(track.relative_path)
        return {"path": track.relative_path}

    return AnalysisPipeline(database, IDENTITY, extract)


def test_pipeline_filters_then_limits_pending_tracks(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")
    _track(database, "one", "Techno/B.flac")
    _track(database, "two", "House/C.flac")
    calls: list[str] = []

    result = _pipeline(database, calls).run(
        source_id="one", path_prefix="House", limit=1, workers=2
    )

    assert result.eligible == 1
    assert result.analyzed == 1
    assert result.reused == result.failed == 0
    assert calls == ["House/A.flac"]


def test_pipeline_reuses_unchanged_tracks_on_a_second_run(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")
    calls: list[str] = []
    pipeline = _pipeline(database, calls)

    first = pipeline.run()
    second = pipeline.run()

    assert first.analyzed == 1
    assert second.eligible == 0
    assert second.analyzed == second.failed == 0
    assert second.reused == second.eligible
    assert calls == ["House/A.flac"]


def test_pipeline_force_selects_reusable_tracks_without_duplicate_persistence(
    tmp_path: Path,
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")
    calls: list[str] = []
    pipeline = _pipeline(database, calls)
    pipeline.run()

    result = pipeline.run(force=True)

    assert result.eligible == result.reused == 1
    assert result.analyzed == result.failed == 0
    assert calls == ["House/A.flac"]
    assert database.scalar("SELECT COUNT(*) FROM audio_analysis") == 1
