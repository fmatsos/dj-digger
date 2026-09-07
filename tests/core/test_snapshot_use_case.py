"""Typed publication contracts for catalog snapshots."""

from pathlib import Path

from dj_digger.core.application import CoreApplication, SnapshotRequest, SnapshotResult
from dj_digger.core.config import LibrarySourceConfig, WorkspaceConfig


def _config(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "library"
    source.mkdir()
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(LibrarySourceConfig("source", source, True, False, True),),
    )


def test_snapshot_returns_typed_result_with_validated_manifest(tmp_path: Path) -> None:
    config = _config(tmp_path)
    output = tmp_path / "snapshot"

    with CoreApplication(config) as core:
        result = core.snapshot(SnapshotRequest(output=output, archive=True))

    assert isinstance(result, SnapshotResult)
    assert result.directory == output
    assert result.archive == tmp_path / "snapshot.tar.gz"
    assert (output / "snapshot-manifest.json").is_file()
    assert (output / "tracks.tsv").is_file()
    assert (output / "library-artifacts.tsv").is_file()
