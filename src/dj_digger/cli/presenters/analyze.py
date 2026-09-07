"""Presentation mapping for typed analysis results."""

from typing import Any

from dj_digger.core.analysis.pipeline import AnalysisRunResult


def analyze_payload(result: AnalysisRunResult) -> dict[str, Any]:
    """Preserve the compact analysis JSON contract at the CLI boundary."""
    failed = int(getattr(result, "failed", 0))
    analyzed = int(getattr(result, "analyzed", 0))
    status = getattr(result, "status", None)
    if status not in {"succeeded", "partial", "failed"}:
        status = "failed" if failed and not analyzed else ("partial" if failed else "succeeded")
    return {
        "event": "analyze",
        "status": status,
        "run_id": getattr(result, "run_id", None),
        "eligible": int(getattr(result, "eligible", 0)),
        "analyzed": analyzed,
        "reused": int(getattr(result, "reused", 0)),
        "failed": failed,
    }
