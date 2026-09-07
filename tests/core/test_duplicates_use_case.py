"""Typed duplicate workflow contracts."""

from pathlib import Path

import pytest

from dj_digger.core.application import (
    CoreApplication,
    DuplicateAnalysisResult,
    DuplicateAnalyzeRequest,
    DuplicateGroupDescription,
    DuplicateListRequest,
    DuplicateMarkBestRequest,
    QualityMarkResult,
    ResourceNotFoundError,
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


def test_duplicate_workflows_return_typed_core_results(tmp_path: Path) -> None:
    with CoreApplication(_config(tmp_path)) as core:
        analyzed = core.duplicates_analyze(DuplicateAnalyzeRequest())
        listed = core.duplicates_list(DuplicateListRequest())
        marked = core.duplicates_mark_best_quality(DuplicateMarkBestRequest())

    assert isinstance(analyzed, DuplicateAnalysisResult)
    assert isinstance(listed, list)
    assert all(isinstance(group, DuplicateGroupDescription) for group in listed)
    assert isinstance(marked, QualityMarkResult)


def test_duplicate_workflows_accept_typed_requests(
    tmp_path: Path,
) -> None:
    with CoreApplication(_config(tmp_path)) as application:
        analyzed = application.duplicates_analyze(DuplicateAnalyzeRequest(source_id="source"))
        listed = application.duplicates_list(DuplicateListRequest(source_id="source"))
        marked = application.duplicates_mark_best_quality(
            DuplicateMarkBestRequest(source_id="source")
        )

    assert isinstance(analyzed, DuplicateAnalysisResult)
    assert listed == []
    assert isinstance(marked, QualityMarkResult)


def test_duplicate_workflows_reject_unknown_sources_as_core_errors(tmp_path: Path) -> None:
    with CoreApplication(_config(tmp_path)) as core:
        with pytest.raises(ResourceNotFoundError, match="unknown or disabled source"):
            core.duplicates_list(DuplicateListRequest(source_id="missing"))
