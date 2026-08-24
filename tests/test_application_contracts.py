"""Focused orchestration contracts for the unified analysis publication."""

import json
from pathlib import Path
from types import SimpleNamespace

from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.analysis.extractor import AnalysisExtractionResult
from dj_digger.analysis.persistence import AnalysisPersistence
from dj_digger.analysis.pipeline import AnalysisRunResult
from dj_digger.application import WorkspaceApplication
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import ScanRunRepository, TrackRepository
from dj_digger.config import ExportConfig, LibrarySourceConfig, WorkspaceConfig


def _workspace(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "library"
    source.mkdir()
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        export=ExportConfig(),
        sources=(LibrarySourceConfig("source", source, True, True, True),),
    )


def _seed_failed_run(application: WorkspaceApplication) -> AnalysisRunResult:
    scan_id = ScanRunRepository(application.database).start("source", scanner_version="test")
    track = TrackRepository(application.database).insert(
        source_id="source", relative_path="Techno/A.flac", filename="A.flac",
        extension=".flac", size_bytes=10, mtime_ns=20, scan_id=scan_id,
    )
    identity = application._analysis_identity
    run_id, analyzed, failed = AnalysisPersistence(application.database).persist_run(
        identity, [(track, {}, "decoder unavailable", "decode")], eligible=1, reused=0,
        started_at="2026-01-01T00:00:00+00:00", finished_at="2026-01-01T00:00:01+00:00",
    )
    return AnalysisRunResult(run_id, 1, analyzed, 0, failed, "failed")


def test_default_adapter_preserves_absolute_source_and_relative_identity(monkeypatch, tmp_path):
    calls = {}

    class StubComposite:
        identity = AnalysisIdentity(2, "dj-digger-analysis/2", "a" * 64)

        def __init__(self, _config):
            pass

        def extract(self, path, **kwargs):
            calls.update(path=path, **kwargs)
            return AnalysisExtractionResult({}, {}, None, "succeeded")

    monkeypatch.setattr("dj_digger.application.CompositeAudioExtractor", StubComposite)
    application = WorkspaceApplication(_workspace(tmp_path))
    track = Track(7, "source", "Techno/track.flac", "track.flac", ".flac", 1, 2, "present")
    application._analysis_extractor(track)
    assert calls == {
        "path": (tmp_path / "library/Techno/track.flac").resolve(),
        "source_id": "source", "track_id": 7, "relative_path": "Techno/track.flac",
    }
    assert application._analysis_identity == StubComposite.identity


def test_refresh_metadata_partial_still_publishes(monkeypatch, tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))
    scans = [SimpleNamespace(succeeded=True, source_id="source")]
    monkeypatch.setattr(application, "scan", lambda **_: scans)
    monkeypatch.setattr(application, "metadata", lambda: SimpleNamespace(status="partial"))
    monkeypatch.setattr(application, "analyze", lambda: SimpleNamespace(status="succeeded"))
    published = []
    monkeypatch.setattr(application, "export", lambda: published.append(True) or ["tracks.tsv"])
    result = application.refresh()
    assert result["status"] == "partial" and result["published"] is True and published


def test_refresh_failed_analysis_still_publishes_failure_audit(monkeypatch, tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))
    failed = _seed_failed_run(application)
    scans = [SimpleNamespace(succeeded=True, source_id="source")]
    monkeypatch.setattr(application, "scan", lambda **_: scans)
    monkeypatch.setattr(application, "metadata", lambda: SimpleNamespace(status="succeeded"))
    monkeypatch.setattr(application, "analyze", lambda: failed)

    result = application.refresh()

    assert result["status"] == "failed"
    assert result["published"] is True
    audit = json.loads((application.config.exports / "dj-analysis-run.json").read_text())
    assert audit["status"] == "failed"
    assert audit["failed"] == 1
    assert audit["failures"][0]["error"] == "decoder unavailable"


def test_refresh_export_exception_preserves_existing_analysis_bytes(monkeypatch, tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))
    _seed_failed_run(application)
    application.config.exports.mkdir(parents=True)
    paths = [
        application.config.exports / name
        for name in ("dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json")
    ]
    before = {}
    for index, path in enumerate(paths):
        content = f"old-{index}".encode()
        path.write_bytes(content)
        before[path] = content
    scans = [SimpleNamespace(succeeded=True, source_id="source")]
    monkeypatch.setattr(application, "scan", lambda **_: scans)
    monkeypatch.setattr(application, "metadata", lambda: SimpleNamespace(status="succeeded"))
    monkeypatch.setattr(application, "analyze", lambda: SimpleNamespace(status="succeeded"))
    def fail_export(*_args, **_kwargs):
        raise RuntimeError("publish failed")

    monkeypatch.setattr(application, "export", fail_export)

    result = application.refresh()

    assert result["status"] == "failed" and result["published"] is False
    assert "publish failed" in result["error"]
    assert {path: path.read_bytes() for path in paths} == before


def test_export_analysis_publishes_only_analysis_facets(tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))
    _seed_failed_run(application)

    published = application.export("analysis")

    assert {Path(path).name for path in published} == {
        "dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json"
    }
    assert not (application.config.exports / "tracks.tsv").exists()
    assert not (application.config.exports / "artifacts.jsonl").exists()


def test_export_all_with_legacy_disabled_has_only_unified_facets(tmp_path):
    config = _workspace(tmp_path)
    config = WorkspaceConfig(config.database, config.exports, ExportConfig(False), config.sources)
    application = WorkspaceApplication(config)
    _seed_failed_run(application)

    application.export("all")

    assert (config.exports / "tracks.tsv").is_file()
    assert all((config.exports / name).is_file() for name in (
        "dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json"
    ))
    assert {path.name for path in config.exports.iterdir()} == {
        "tracks.tsv", "library-artifacts.tsv", "dj-analysis.tsv",
        "dj-sections.jsonl", "dj-analysis-run.json",
    }


def test_status_reports_analysis_facet_booleans_and_latest_identity(tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))
    _seed_failed_run(application)
    application.config.exports.mkdir(parents=True, exist_ok=True)
    (application.config.exports / "dj-analysis.tsv").write_text("header\n")
    (application.config.exports / "dj-analysis-run.json").write_text("{}\n")

    result = application.status()

    assert set(result["exports"]["analysis"]) == {
        "dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json"
    }
    assert result["exports"]["analysis"] == {
        "dj-analysis.tsv": True, "dj-sections.jsonl": False, "dj-analysis-run.json": True
    }
    identity = result["latest_analysis"]["identity"]
    assert identity == {
        "schema_version": application._analysis_identity.schema_version,
        "analyzer_version": application._analysis_identity.analyzer_version,
        "config_hash": application._analysis_identity.config_hash,
    }
