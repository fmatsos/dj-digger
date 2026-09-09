"""Scan command adapter."""

from typing import Any

from dj_digger.cli.presenters.scan import scan_payload
from dj_digger.core.application import CoreApplication, ScanRequest


def execute(service: CoreApplication, request: ScanRequest) -> dict[str, Any]:
    """Execute one typed scan request through the core boundary."""
    return scan_payload(service.scan(request))


__all__ = ["execute"]
