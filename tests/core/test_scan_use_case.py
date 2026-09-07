"""Typed scan use-case contracts."""

from pathlib import Path

from dj_digger.config import LibrarySourceConfig, WorkspaceConfig
from dj_digger.core.application import CoreApplication, ScanRequest, ScanRunResult, ScanSourceResult
from dj_digger.core.catalog.database import Database


def workspace_config(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "library"
    source.mkdir()
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(LibrarySourceConfig("source", source, True, False, True),),
    )


def test_scan_returns_typed_source_results(tmp_path: Path) -> None:
    config = workspace_config(tmp_path)
    with CoreApplication(config) as core:
        result = core.scan(ScanRequest())

    assert isinstance(result, ScanRunResult)
    assert all(isinstance(item, ScanSourceResult) for item in result.sources)
    with Database.open(config.database) as database:
        assert database.scalar("SELECT COUNT(*) FROM scan_runs") == 1
        assert database.scalar("SELECT status FROM scan_runs") == "succeeded"
