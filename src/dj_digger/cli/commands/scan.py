"""Scan command adapter."""

from dj_digger.cli.presenters.scan import scan_payload
from dj_digger.core.application import CoreApplication, ScanRequest
from dj_digger.core.diagnostics import Diagnostic


def execute(service: CoreApplication, request: ScanRequest) -> Diagnostic:
    """Execute one typed scan request through the core boundary."""
    return scan_payload(service.scan(request))


__all__ = ["execute"]
