"""Deterministic serialization shared by persisted analysis facts."""

import json
from collections.abc import Mapping
from typing import Any


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Encode an analysis payload in a stable form suitable for storage."""
    return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)
