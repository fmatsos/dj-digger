"""Analysis command adapter."""

from inspect import signature
from typing import Any

from dj_digger.cli.presenters.analyze import analyze_payload
from dj_digger.core.application import AnalyzeRequest, CoreApplication
from dj_digger.core.application.progress import ProgressSink


def execute(
    service: CoreApplication,
    request: AnalyzeRequest,
    *,
    progress: ProgressSink | None = None,
) -> dict[str, Any]:
    """Execute one typed analysis request through the core boundary."""
    analyze = service.analyze
    if "request" in signature(analyze).parameters:
        result = analyze(request, progress=progress)
    else:
        result = analyze(
            request.source_id,
            path_prefix=request.path_prefix,
            limit=request.limit,
            force=request.force,
            workers=request.workers,
            track_timeout=request.track_timeout,
            progress=progress,
        )
    return analyze_payload(result)
