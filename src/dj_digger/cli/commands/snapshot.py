"""CLI adapter for the typed snapshot use case."""

from typing import Any

from dj_digger.cli.presenters.snapshot import snapshot_payload
from dj_digger.core.application import SnapshotRequest


def execute(service: Any, request: SnapshotRequest) -> dict[str, Any]:
    """Execute a snapshot request and preserve the historical JSON payload."""
    return snapshot_payload(service.snapshot(request))


__all__ = ["execute"]
