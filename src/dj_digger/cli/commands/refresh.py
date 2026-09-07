"""CLI adapter for the typed refresh use case."""

from inspect import signature
from typing import Any

from dj_digger.cli.presenters.refresh import refresh_payload
from dj_digger.core.application import CoreApplication, RefreshRequest
from dj_digger.core.application.progress import ProgressSink


def execute(
    service: CoreApplication,
    request: RefreshRequest,
    *,
    progress: ProgressSink | None = None,
) -> dict[str, Any]:
    """Execute one refresh request through the core boundary."""

    refresh = service.refresh
    if "request" in signature(refresh).parameters:
        result = refresh(request, progress=progress)
    else:
        result = refresh(
            progress=progress,
            workers=request.workers,
            track_timeout=request.track_timeout,
        )
    return refresh_payload(result)


__all__ = ["execute"]
