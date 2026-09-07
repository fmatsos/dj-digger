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
    result = service.analyze(request, progress=progress)
    return analyze_payload(result)
