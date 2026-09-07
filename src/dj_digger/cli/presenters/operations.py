"""Presentation mapping for typed operational results."""

from collections.abc import Mapping
from typing import Any, cast


def operation_payload(result: Any) -> dict[str, Any]:
    """Convert a typed result (or legacy mapping) to the CLI payload."""
    if hasattr(result, "as_dict"):
        return cast(dict[str, Any], result.as_dict())
    if isinstance(result, Mapping):
        return dict(result)
    raise TypeError(f"unsupported operation result: {type(result).__name__}")


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
