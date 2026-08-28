"""Focused orchestration contracts for the unified analysis publication."""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.analysis.persistence import AnalysisOutcome, AnalysisPersistence
from dj_digger.analysis.pipeline import AnalysisRunResult
from dj_digger.application import WorkspaceApplication
from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository
from dj_digger.config import LibrarySourceConfig, WorkspaceConfig


class RecordingProgress:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    def phase_started(self, name: str, completed: int, total: int) -> None:
        self.events.append(("started", name, completed, total))

    def phase_finished(self, name: str, completed: int, total: int) -> None:
        self.events.append(("finished", name, completed, total))

    def analysis_started(self, *, total: int, completed: int) -> None:
        self.events.append(("analysis_started", total, completed))

    def analysis_advanced(self) -> None:
        self.events.append(("analysis_advanced",))

    def analysis_finished(self) -> None:
        self.events.append(("analysis_finished",))


def _workspace(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "library"
    source.mkdir()
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(LibrarySourceConfig("source", source, True, True, True),),
    )


def test_configured_sources_are_synchronized_atomically(monkeypatch, tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    config = WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(
            LibrarySourceConfig("first", first_root, True, True, True),
            LibrarySourceConfig("second", second_root, True, True, True),
        ),
    )
    original_upsert = SourceRepository.upsert
    original_open = Database.open
    opened_databases: list[Database] = []

    def record_open(path: Path) -> Database:
        database = original_open(path)
        opened_databases.append(database)
        return database

    def fail_on_second(self, source_id, *args, **kwargs):
        original_upsert(self, source_id, *args, **kwargs)
        if source_id == "second":
            raise RuntimeError("second source rejected")

    monkeypatch.setattr("dj_digger.application.Database.open", record_open)
    monkeypatch.setattr(SourceRepository, "upsert", fail_on_second)

    with pytest.raises(RuntimeError, match="second source rejected"):
        WorkspaceApplication(config)

    assert len(opened_databases) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        opened_databases[0].scalar("SELECT 1")
    with original_open(config.database) as database:
        assert database.scalar("SELECT COUNT(*) FROM library_sources") == 0


def test_track_insert_rolls_back_with_its_caller_transaction(tmp_path: Path) -> None:
    application = WorkspaceApplication(_workspace(tmp_path))
    scan_id = ScanRunRepository(application.database).start("source", scanner_version="test")

    with pytest.raises(RuntimeError, match="abort track insert"):
        with application.database.transaction():
            TrackRepository(application.database).insert(
                source_id="source",
                relative_path="Techno/A.flac",
                filename="A.flac",
                extension=".flac",
                size_bytes=10,
                mtime_ns=20,
                scan_id=scan_id,
            )
            raise RuntimeError("abort track insert")

    assert application.database.scalar("SELECT COUNT(*) FROM tracks") == 0


def test_workspace_application_context_closes_its_database(tmp_path: Path) -> None:
    with WorkspaceApplication(_workspace(tmp_path)) as application:
        database = application.database

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        database.scalar("SELECT 1")


def _seed_failed_run(application: WorkspaceApplication) -> AnalysisRunResult:
    scan_id = ScanRunRepository(application.database).start("source", scanner_version="test")
    with application.database.transaction():
        track = TrackRepository(application.database).insert(
            source_id="source",
            relative_path="Techno/A.flac",
            filename="A.flac",
            extension=".flac",
            size_bytes=10,
            mtime_ns=20,
            scan_id=scan_id,
        )
    identity = application._analysis_identity
    persistence = AnalysisPersistence(application.database)
    run_id = persistence.start_run(
        identity, eligible=1, reused=0, started_at="2026-01-01T00:00:00+00:00"
    )
    analyzed, failed = persistence.persist_outcome(
        run_id,
        identity,
        AnalysisOutcome(track, {}, "decoder unavailable", "decode"),
        occurred_at="2026-01-01T00:00:01+00:00",
    )
    persistence.finish_run(run_id, finished_at="2026-01-01T00:00:01+00:00")
    return AnalysisRunResult(run_id, 1, analyzed, 0, failed, "failed")


def test_default_adapter_wires_isolated_source_root_and_identity(monkeypatch, tmp_path):
    calls = {}

    class StubIsolated:
        def __init__(self, source_roots, dsp):
            calls.update(source_roots=source_roots, dsp=dsp)

    monkeypatch.setattr("dj_digger.application.IsolatedAnalysisExtractor", StubIsolated)
    application = WorkspaceApplication(_workspace(tmp_path))
    assert calls["source_roots"] == {"source": (tmp_path / "library").resolve()}
    assert calls["dsp"] == application.config.dsp
    assert application._analysis_identity == AnalysisIdentity(
        2, "dj-digger-analysis/3", application.config.dsp.config_hash
    )


def test_refresh_metadata_partial_still_publishes(monkeypatch, tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))
    scans = [SimpleNamespace(succeeded=True, source_id="source")]
    monkeypatch.setattr(application, "scan", lambda **_: scans)
    monkeypatch.setattr(application, "metadata", lambda: SimpleNamespace(status="partial"))
    monkeypatch.setattr(application, "analyze", lambda **_: SimpleNamespace(status="succeeded"))
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
    monkeypatch.setattr(application, "analyze", lambda **_: failed)

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
    monkeypatch.setattr(application, "analyze", lambda **_: SimpleNamespace(status="succeeded"))

    def fail_export(*_args, **_kwargs):
        raise RuntimeError("publish failed")

    monkeypatch.setattr(application, "export", fail_export)

    result = application.refresh()

    assert result["status"] == "failed" and result["published"] is False
    assert "publish failed" in result["error"]
    assert {path: path.read_bytes() for path in paths} == before


def test_refresh_reports_the_four_phases_in_order(monkeypatch, tmp_path: Path) -> None:
    application = WorkspaceApplication(_workspace(tmp_path))
    progress = RecordingProgress()
    scans = [SimpleNamespace(succeeded=True, source_id="source")]
    monkeypatch.setattr(application, "scan", lambda **_: scans)
    monkeypatch.setattr(application, "metadata", lambda: SimpleNamespace(status="succeeded"))
    monkeypatch.setattr(
        application,
        "analyze",
        lambda **_: SimpleNamespace(status="succeeded"),
    )
    monkeypatch.setattr(application, "export", lambda: ["tracks.tsv"])

    application.refresh(progress=progress)

    assert progress.events == [
        ("started", "scan", 0, 4),
        ("finished", "scan", 1, 4),
        ("started", "metadata", 1, 4),
        ("finished", "metadata", 2, 4),
        ("started", "analysis", 2, 4),
        ("finished", "analysis", 3, 4),
        ("started", "exports", 3, 4),
        ("finished", "exports", 4, 4),
    ]


def test_refresh_stops_progress_after_a_required_scan_failure(monkeypatch, tmp_path: Path) -> None:
    application = WorkspaceApplication(_workspace(tmp_path))
    progress = RecordingProgress()
    monkeypatch.setattr(
        application,
        "scan",
        lambda **_: [SimpleNamespace(succeeded=False, source_id="source")],
    )

    result = application.refresh(progress=progress)

    assert result["published"] is False
    assert progress.events == [
        ("started", "scan", 0, 4),
        ("finished", "scan", 1, 4),
    ]


def test_export_analysis_publishes_only_analysis_facets(tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))
    _seed_failed_run(application)

    published = application.export("analysis")

    assert {Path(path).name for path in published} == {
        "dj-analysis.tsv",
        "dj-sections.jsonl",
        "dj-analysis-run.json",
    }
    assert not (application.config.exports / "tracks.tsv").exists()
    assert not (application.config.exports / "artifacts.jsonl").exists()


def test_export_all_has_only_canonical_facets(tmp_path):
    config = _workspace(tmp_path)
    application = WorkspaceApplication(config)
    _seed_failed_run(application)

    application.export("all")

    assert (config.exports / "tracks.tsv").is_file()
    assert all(
        (config.exports / name).is_file()
        for name in ("dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json")
    )
    assert {path.name for path in config.exports.iterdir()} == {
        "tracks.tsv",
        "library-artifacts.tsv",
        "dj-analysis.tsv",
        "dj-sections.jsonl",
        "dj-analysis-run.json",
    }


def test_export_tracks_json_projects_requested_fields_in_order(tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))

    published = application.export(type="tracks", format="json", fields="title,filename")

    assert [Path(path).name for path in published] == ["tracks.json"]
    assert json.loads(Path(published[0]).read_text(encoding="utf-8")) == []


def test_export_all_csv_applies_the_format_to_every_leaf(tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))
    _seed_failed_run(application)

    published = application.export(type="all", format="csv")

    assert {Path(path).name for path in published} == {
        "tracks.csv",
        "library-artifacts.csv",
        "dj-analysis.csv",
        "dj-sections.csv",
        "dj-analysis-run.csv",
    }


@pytest.mark.parametrize(
    ("type_", "fields", "message"),
    [
        (None, "title", "--fields requires a leaf --type"),
        ("all", "title", "--fields requires a leaf --type"),
        ("tracks", "title,title", "--fields contains duplicate fields"),
        ("tracks", "bpm", "unknown field: bpm"),
    ],
)
def test_export_rejects_invalid_field_selection_before_publication(
    tmp_path, type_, fields, message
):
    application = WorkspaceApplication(_workspace(tmp_path))

    with pytest.raises(ValueError, match=message):
        application.export(type=type_, fields=fields)

    assert not application.config.exports.exists() or not any(application.config.exports.iterdir())


def test_status_reports_analysis_facet_booleans_and_latest_identity(tmp_path):
    application = WorkspaceApplication(_workspace(tmp_path))
    _seed_failed_run(application)
    application.config.exports.mkdir(parents=True, exist_ok=True)
    (application.config.exports / "dj-analysis.tsv").write_text("header\n")
    (application.config.exports / "dj-analysis-run.json").write_text("{}\n")

    result = application.status()

    assert set(result["exports"]["analysis"]) == {
        "dj-analysis.tsv",
        "dj-sections.jsonl",
        "dj-analysis-run.json",
    }
    assert result["exports"]["analysis"] == {
        "dj-analysis.tsv": True,
        "dj-sections.jsonl": False,
        "dj-analysis-run.json": True,
    }
    identity = result["latest_analysis"]["identity"]
    assert identity == {
        "schema_version": application._analysis_identity.schema_version,
        "analyzer_version": application._analysis_identity.analyzer_version,
        "config_hash": application._analysis_identity.config_hash,
    }
