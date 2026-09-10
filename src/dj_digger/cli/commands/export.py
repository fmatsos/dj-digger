"""CLI adapter for the typed export use case."""

from dj_digger.cli.presenters.export import export_payload
from dj_digger.core.application import CoreApplication, ExportRequest
from dj_digger.core.diagnostics import Diagnostic


def execute(service: CoreApplication, request: ExportRequest) -> Diagnostic:
    """Execute an export request and preserve the historical JSON payload."""
    return export_payload(service.export(request))


__all__ = ["execute"]
