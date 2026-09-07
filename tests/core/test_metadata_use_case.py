"""Typed metadata use-case contracts."""

from pathlib import Path

import pytest

from dj_digger.core.application import CoreApplication, InvalidInputError
from dj_digger.core.application.metadata import MetadataRequest, MetadataRunResult
from dj_digger.core.catalog.database import Database
from dj_digger.core.catalog.repositories import ScanRunRepository, TrackRepository
from dj_digger.core.config import LibrarySourceConfig, WorkspaceConfig


def workspace_config(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "library"
    source.mkdir()
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(LibrarySourceConfig("source", source, True, False, True),),
    )


def test_metadata_rejects_blank_path_prefix(tmp_path: Path) -> None:
    with CoreApplication(workspace_config(tmp_path)) as core:
        with pytest.raises(InvalidInputError, match="path prefix must not be blank"):
            core.metadata(MetadataRequest(path_prefix="  "))


def test_metadata_returns_typed_result_and_persists_embedded_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = workspace_config(tmp_path)
    with CoreApplication(config) as core:
        run_id = ScanRunRepository(core.database).start("source", scanner_version="test")
        with core.database.transaction():
            track = TrackRepository(core.database).insert(
                source_id="source",
                relative_path="Track.flac",
                filename="Track.flac",
                extension=".flac",
                size_bytes=1,
                mtime_ns=2,
                scan_id=run_id,
            )

        def run(argv: list[str], **_kwargs: object) -> object:
            if argv[-1] == "-ver":
                return type("Result", (), {"stdout": "12.99\n", "returncode": 0})()
            return type(
                "Result",
                (),
                {
                    "stdout": (
                        '[{"SourceFile":"'
                        + str(config.sources[0].path / track.relative_path)
                        + '","Title":"Embedded title"}]'
                    ),
                    "returncode": 0,
                },
            )()

        monkeypatch.setattr("dj_digger.core.metadata.exiftool.subprocess.run", run)
        result = core.metadata(MetadataRequest())

    assert isinstance(result, MetadataRunResult)
    assert result.extracted == 1
    assert result.failed == 0
    with Database.open(config.database) as database:
        assert (
            database.scalar("SELECT title FROM embedded_metadata WHERE track_id = ?", (track.id,))
            == "Embedded title"
        )
