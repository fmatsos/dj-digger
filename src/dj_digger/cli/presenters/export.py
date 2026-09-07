"""Presentation mapping for typed export results."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dj_digger.core.application import ExportResult


def export_payload(result: ExportResult | Sequence[str] | Sequence[Path]) -> dict[str, Any]:
    """Preserve the compact export JSON contract at the CLI boundary."""
    if isinstance(result, ExportResult):
        paths = [str(path) for path in result.paths]
    else:
        paths = [str(path) for path in result]
    return {"event": "export", "status": "succeeded", "exports": paths}


__all__ = ["export_payload"]
