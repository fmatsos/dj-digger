"""Duplicate command adapter from Typer-facing options to core requests."""

from typing import Any, cast

from dj_digger.cli.presenters.duplicates import (
    duplicate_analysis_payload,
    duplicate_groups_payload,
    duplicate_mark_best_payload,
)
from dj_digger.core.application import (
    CoreApplication,
    DuplicateAnalysisResult,
    DuplicateAnalyzeRequest,
    DuplicateListRequest,
    DuplicateMarkBestRequest,
    QualityMarkResult,
)
from dj_digger.core.application.progress import ProgressSink


def execute(
    service: CoreApplication,
    request: DuplicateAnalyzeRequest | DuplicateListRequest | DuplicateMarkBestRequest,
    *,
    progress: ProgressSink | None = None,
    dj_review: bool = False,
) -> dict[str, Any]:
    """Invoke one focused duplicate workflow and return its presenter payload."""
    if isinstance(request, DuplicateAnalyzeRequest):
        result = service.duplicates_analyze(request, progress=progress)
        return duplicate_analysis_payload(cast(DuplicateAnalysisResult, result))
    if isinstance(request, DuplicateListRequest):
        groups = service.duplicates_list(request)
        return duplicate_groups_payload(groups, dj_review=dj_review)
    result = service.duplicates_mark_best_quality(request)
    return duplicate_mark_best_payload(cast(QualityMarkResult, result))


__all__ = ["execute"]
