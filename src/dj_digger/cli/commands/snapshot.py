"""CLI adapter for the typed snapshot use case."""

from dj_digger.cli.presenters.snapshot import snapshot_payload
from dj_digger.core.application import CoreApplication, SnapshotRequest
from dj_digger.core.diagnostics import Diagnostic


def execute(service: CoreApplication, request: SnapshotRequest) -> Diagnostic:
    """Execute a snapshot request and preserve the historical JSON payload."""
    return snapshot_payload(service.snapshot(request))


__all__ = ["execute"]
