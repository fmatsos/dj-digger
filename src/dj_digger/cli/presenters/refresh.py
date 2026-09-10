"""Presentation mapping for typed refresh results."""

from collections.abc import Mapping
from typing import Any

from dj_digger.core.application.refresh import RefreshResult
from dj_digger.core.diagnostics import DiagnosticStatus, open_diagnostic


def refresh_payload(result: RefreshResult | Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable machine-readable refresh payload."""

    fields = dict(result.as_dict() if isinstance(result, RefreshResult) else result)
    event = str(fields.pop("event", "refresh"))
    status = str(fields.pop("status", DiagnosticStatus.SUCCEEDED))
    return open_diagnostic(event, status, **fields)


__all__ = ["refresh_payload"]
