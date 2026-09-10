"""Presentation mapping for typed operational results."""

from collections.abc import Mapping
from typing import Any, cast

from dj_digger.core.diagnostics import DiagnosticStatus, open_diagnostic
from dj_digger.core.errors import InvalidInputError


def operation_payload(result: Any) -> dict[str, Any]:
    """Convert a typed operational result to its CLI payload.

    Operational results carry different fields per command, so the payload is
    open; the envelope is still enforced by ``open_diagnostic``.
    """
    if hasattr(result, "as_dict"):
        fields = dict(cast("dict[str, Any]", result.as_dict()))
    elif isinstance(result, Mapping):
        fields = dict(result)
    else:
        raise InvalidInputError(f"unsupported operation result: {type(result).__name__}")
    event = str(fields.pop("event", "operation"))
    status = str(fields.pop("status", DiagnosticStatus.SUCCEEDED))
    return open_diagnostic(event, status, **fields)


status_payload = operation_payload
doctor_payload = operation_payload
optimize_payload = operation_payload
quick_check_payload = operation_payload
integrity_check_payload = operation_payload
rebuild_payload = operation_payload


__all__ = [
    "doctor_payload",
    "integrity_check_payload",
    "operation_payload",
    "optimize_payload",
    "quick_check_payload",
    "rebuild_payload",
    "status_payload",
]
