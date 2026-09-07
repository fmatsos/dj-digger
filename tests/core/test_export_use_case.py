"""Typed publication contracts for catalog exports."""

from pathlib import Path

import pytest

from dj_digger.core.application import (
    CoreApplication,
    ExportRequest,
    ExportResult,
    InvalidInputError,
)
from dj_digger.core.config import LibrarySourceConfig, WorkspaceConfig


def _config(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "library"
    source.mkdir()
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(LibrarySourceConfig("source", source, True, False, True),),
    )


def test_export_returns_typed_facets_and_row_counts(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with CoreApplication(config) as core:
        result = core.export(ExportRequest(facet="tracks"))

    assert isinstance(result, ExportResult)
    assert [(facet.path.name, facet.row_count) for facet in result.facets] == [("tracks.tsv", 0)]
    assert result.paths == (config.exports / "tracks.tsv",)


@pytest.mark.parametrize(
    ("export_request", "message"),
    [
        (ExportRequest(facet="unknown"), "unknown export facet"),
        (ExportRequest(type="tracks", fields="unknown"), "unknown field"),
    ],
)
def test_export_rejects_unknown_selection_at_core_boundary(
    tmp_path: Path, export_request: ExportRequest, message: str
) -> None:
    config = _config(tmp_path)

    with CoreApplication(config) as core:
        with pytest.raises(InvalidInputError, match=message):
            core.export(export_request)

    assert not config.exports.exists()
