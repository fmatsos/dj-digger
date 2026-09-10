"""Presentation mapping for typed export results."""

from collections.abc import Sequence
from pathlib import Path

from dj_digger.core.application import ExportResult
from dj_digger.core.diagnostics import ExportDiagnostic


def export_payload(result: ExportResult | Sequence[str] | Sequence[Path]) -> ExportDiagnostic:
    """Preserve the compact export JSON contract at the CLI boundary."""
    if isinstance(result, ExportResult):
        paths = [str(path) for path in result.paths]
    else:
        paths = [str(path) for path in result]
    return {"event": "export", "status": "succeeded", "exports": paths}


__all__ = ["export_payload"]
