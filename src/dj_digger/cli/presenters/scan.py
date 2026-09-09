"""Presentation mapping for typed scan results."""

from typing import Any

from dj_digger.core.application import ScanRunResult
from dj_digger.core.diagnostics import DiagnosticStatus


def scan_payload(result: ScanRunResult) -> dict[str, Any]:
    """Preserve the compact scan JSON contract at the CLI boundary."""
    scans = [
        {
            "source_id": item.source_id,
            "succeeded": item.succeeded,
            "run_id": item.run_id,
            "error": item.error,
        }
        for item in result.sources
    ]
    return {
        "event": "scan",
        "status": (
            DiagnosticStatus.SUCCEEDED
            if all(item["succeeded"] for item in scans)
            else DiagnosticStatus.FAILED
        ),
        "scans": scans,
    }
