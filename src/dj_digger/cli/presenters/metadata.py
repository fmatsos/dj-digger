"""Presentation mapping for typed metadata results."""

from typing import Any

from dj_digger.core.application import MetadataRunResult


def metadata_payload(result: MetadataRunResult) -> dict[str, Any]:
    """Preserve the compact metadata JSON contract at the CLI boundary."""
    return {
        "event": "metadata",
        "status": result.status,
        "extracted": result.extracted,
        "failed": result.failed,
        "skipped": result.skipped,
    }
