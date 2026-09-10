"""Duplicate command adapters, one per focused workflow.

Three separate entry points replace a single union-typed function that had to
re-discover its own workflow with ``isinstance`` and two casts.
"""

from typing import Any

from dj_digger.cli.presenters.duplicates import (
    duplicate_analysis_payload,
    duplicate_groups_payload,
    duplicate_mark_best_payload,
)
from dj_digger.core.application import (
    CoreApplication,
    DuplicateAnalyzeRequest,
    DuplicateListRequest,
    DuplicateMarkBestRequest,
)
from dj_digger.core.progress import ProgressSink


def execute_analyze(
    service: CoreApplication,
    request: DuplicateAnalyzeRequest,
    *,
    progress: ProgressSink | None = None,
) -> dict[str, Any]:
    """Fingerprint present tracks and report the resulting duplicate groups."""
    return duplicate_analysis_payload(service.duplicates_analyze(request, progress=progress))


def execute_list(
    service: CoreApplication, request: DuplicateListRequest, *, dj_review: bool = False
) -> dict[str, Any]:
    """List known duplicate groups without touching the catalog."""
    return duplicate_groups_payload(service.duplicates_list(request), dj_review=dj_review)


def execute_mark_best(
    service: CoreApplication, request: DuplicateMarkBestRequest
) -> dict[str, Any]:
    """Mark the best-quality copy in each duplicate group."""
    return duplicate_mark_best_payload(service.duplicates_mark_best_quality(request))


__all__ = ["execute_analyze", "execute_list", "execute_mark_best"]
