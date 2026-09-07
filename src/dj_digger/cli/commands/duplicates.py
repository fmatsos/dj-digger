"""Duplicate command adapter from Typer-facing options to core requests."""

from inspect import signature
from typing import Any, cast

from dj_digger.cli.presenters.duplicates import (
    duplicate_analysis_payload,
    duplicate_groups_payload,
    duplicate_mark_best_payload,
)
from dj_digger.core.application import (
    DuplicateAnalysisResult,
    DuplicateAnalyzeRequest,
    DuplicateListRequest,
    DuplicateMarkBestRequest,
    QualityMarkResult,
)
from dj_digger.core.application.progress import ProgressSink
from dj_digger.core.duplicates.service import DuplicateGroupDescription


def execute(
    service: Any,
    request: DuplicateAnalyzeRequest | DuplicateListRequest | DuplicateMarkBestRequest,
    *,
    progress: ProgressSink | None = None,
    dj_review: bool = False,
) -> dict[str, Any]:
    """Invoke one focused duplicate workflow and return its presenter payload."""
    if isinstance(request, DuplicateAnalyzeRequest):
        result = _invoke(
            service,
            "duplicates_analyze",
            request,
            request.source_id,
            progress=progress,
        )
        return duplicate_analysis_payload(cast(DuplicateAnalysisResult, result))
    if isinstance(request, DuplicateListRequest):
        groups = _invoke(service, "duplicates_list", request, request.source_id)
        return duplicate_groups_payload(groups, dj_review=dj_review)
    result = _invoke(service, "duplicates_mark_best_quality", request, request.source_id)
    return duplicate_mark_best_payload(cast(QualityMarkResult, result))


def _invoke(
    service: Any,
    method_name: str,
    request: DuplicateAnalyzeRequest | DuplicateListRequest | DuplicateMarkBestRequest,
    legacy_source_id: str | None,
    *,
    progress: ProgressSink | None = None,
) -> DuplicateAnalysisResult | list[DuplicateGroupDescription] | QualityMarkResult:
    method = getattr(service, method_name)
    parameters = signature(method).parameters
    if "request" in parameters:
        if progress is None:
            return method(request)
        return method(request, progress=progress)
    if not isinstance(request, DuplicateAnalyzeRequest):
        return method(legacy_source_id)
    if progress is None:
        return method(
            legacy_source_id,
            workers=request.workers,
            track_timeout=request.track_timeout,
            mark_best_quality=request.mark_best_quality,
            mastering=request.mastering,
        )
    return method(
        legacy_source_id,
        workers=request.workers,
        track_timeout=request.track_timeout,
        mark_best_quality=request.mark_best_quality,
        mastering=request.mastering,
        progress=progress,
    )


__all__ = ["execute"]
