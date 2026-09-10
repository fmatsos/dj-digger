"""CLI adapter for the typed refresh use case."""

from typing import Any

from dj_digger.cli.presenters.refresh import refresh_payload
from dj_digger.core.application import CoreApplication, RefreshRequest
from dj_digger.core.progress import ProgressSink


def execute(
    service: CoreApplication,
    request: RefreshRequest,
    *,
    progress: ProgressSink | None = None,
) -> dict[str, Any]:
    """Execute one refresh request through the core boundary."""

    result = service.refresh(request, progress=progress)
    return refresh_payload(result)


__all__ = ["execute"]
