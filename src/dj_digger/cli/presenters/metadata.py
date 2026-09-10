"""Presentation mapping for typed metadata results."""

from dj_digger.core.application import MetadataRunResult
from dj_digger.core.diagnostics import MetadataDiagnostic


def metadata_payload(result: MetadataRunResult) -> MetadataDiagnostic:
    """Preserve the compact metadata JSON contract at the CLI boundary."""
    return {
        "event": "metadata",
        "status": result.status,
        "extracted": result.extracted,
        "failed": result.failed,
        "skipped": result.skipped,
    }
