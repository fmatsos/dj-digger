"""Presentation mapping for typed refresh results."""

from collections.abc import Mapping
from typing import Any

from dj_digger.core.application.refresh import RefreshResult


def refresh_payload(result: RefreshResult | Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable machine-readable refresh payload."""

    if isinstance(result, RefreshResult):
        return result.as_dict()
    return dict(result)


__all__ = ["refresh_payload"]
