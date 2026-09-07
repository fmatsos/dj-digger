"""CLI adapter for the typed export use case."""

from typing import Any

from dj_digger.cli.presenters.export import export_payload
from dj_digger.core.application import ExportRequest


def execute(service: Any, request: ExportRequest) -> dict[str, Any]:
    """Execute an export request and preserve the historical JSON payload."""
    return export_payload(service.export(request))


__all__ = ["execute"]
