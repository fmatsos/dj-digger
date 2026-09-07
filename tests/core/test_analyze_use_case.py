"""Typed analysis use-case contracts."""

from pathlib import Path

from dj_digger.core.analysis.pipeline import AnalysisRunResult
from dj_digger.core.application import AnalyzeRequest, CoreApplication, ProgressEvent
from dj_digger.core.catalog.repositories import ScanRunRepository, TrackRepository
from dj_digger.core.config import LibrarySourceConfig, WorkspaceConfig


def _config(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "library"
    source.mkdir()
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(LibrarySourceConfig("source", source, True, True, True),),
    )


def test_analyze_delegates_typed_request_and_emits_core_events(tmp_path: Path) -> None:
    config = _config(tmp_path)
    events: list[ProgressEvent] = []
    with CoreApplication(
        config, analysis_extractor=lambda track: {"path": track.relative_path}
    ) as core:
        scan_id = ScanRunRepository(core.database).start("source", scanner_version="test")
        with core.database.transaction():
            TrackRepository(core.database).insert(
                source_id="source",
                relative_path="House/track.flac",
                filename="track.flac",
                extension=".flac",
                size_bytes=10,
                mtime_ns=20,
                scan_id=scan_id,
            )
        result = core.analyze(
            AnalyzeRequest(source_id="source", path_prefix="House", limit=1),
            progress=events.append,
        )

    assert isinstance(result, AnalysisRunResult)
    assert result.analyzed == 1
    assert [event.kind for event in events] == [
        "analysis_started",
        "analysis_advanced",
        "analysis_finished",
    ]
    assert all(event.__class__.__module__.startswith("dj_digger.core") for event in events)
