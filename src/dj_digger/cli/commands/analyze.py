"""Analysis command adapter."""

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
    return analyze_payload(
        service.analyze(
            request.source_id,
            path_prefix=request.path_prefix,
            limit=request.limit,
            force=request.force,
            workers=request.workers,
            track_timeout=request.track_timeout,
            progress=progress,
        )
    )
