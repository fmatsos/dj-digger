"""Presentation mapping for typed snapshot results."""

from dj_digger.core.application import SnapshotResult
from dj_digger.core.diagnostics import SnapshotDiagnostic


def snapshot_payload(result: SnapshotResult) -> SnapshotDiagnostic:
    """Preserve the compact snapshot JSON contract at the CLI boundary."""
    return {
        "event": "snapshot",
        "status": "succeeded",
        "directory": str(result.directory),
        "archive": None if result.archive is None else str(result.archive),
    }


__all__ = ["snapshot_payload"]
