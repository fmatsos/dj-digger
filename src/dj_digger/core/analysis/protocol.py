"""Bounded JSON protocol primitives shared by the analysis parent and worker."""

import json
from collections.abc import Mapping
from typing import Any, BinaryIO

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1024 * 1024


def encode_request(request: Mapping[str, object]) -> bytes:
    """Serialize a request and reject it before spawning an oversized worker input."""
    encoded = json.dumps(request, separators=(",", ":")).encode()
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("analysis worker request is too large")
    return encoded


def read_request(stream: BinaryIO) -> Any:
    """Read at most one byte beyond the request bound before decoding JSON."""
    raw = stream.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        raise ValueError("analysis worker request is too large")
    return json.loads(raw)
