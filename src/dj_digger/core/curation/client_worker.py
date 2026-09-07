"""Bounded subprocess worker for one curation model completion.

This module intentionally knows only about the HTTP client protocol. It never
opens the catalog or imports the curation agent, so the parent can terminate it
without leaving SQLite or application state in a worker process.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import fields
from typing import Any

from dj_digger.core.config import CurationConfig
from dj_digger.core.curation.client import (
    CurationAuthenticationError,
    CurationResponseError,
    CurationTimeoutError,
    CurationTransportError,
    OpenAICompatibleClient,
)

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1_000_000
MAX_RESPONSE_BYTES = 1_000_000


def _error_code(error: Exception) -> str:
    if isinstance(error, CurationAuthenticationError):
        return "authentication"
    if isinstance(error, CurationTimeoutError):
        return "timeout"
    if isinstance(error, CurationResponseError):
        return "response"
    if isinstance(error, CurationTransportError):
        return "transport"
    return "transport"


def _response(
    *,
    message: dict[str, Any] | None = None,
    error: str | None = None,
    detail: str | None = None,
) -> bytes:
    value: dict[str, Any] = {"protocol_version": PROTOCOL_VERSION, "ok": error is None}
    if message is not None:
        value["message"] = message
    if error is not None:
        value["error"] = error
    if detail is not None:
        value["detail"] = detail[:2_000]
    return json.dumps(value, separators=(",", ":")).encode()


def _config(value: object) -> CurationConfig:
    if not isinstance(value, dict):
        raise ValueError("invalid curation worker config")
    names = {field.name for field in fields(CurationConfig)}
    if set(value) != names:
        raise ValueError("invalid curation worker config")
    return CurationConfig(**value)


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        sys.stdout.buffer.write(_response(error="response"))
        return 0
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("protocol_version") != PROTOCOL_VERSION:
            raise ValueError("invalid curation worker protocol")
        config = _config(value.get("config"))
        messages = value["messages"]
        tools = value["tools"]
        if not isinstance(messages, list) or not isinstance(tools, list):
            raise ValueError("invalid curation worker request")
        result = OpenAICompatibleClient(config, os.environ.get(config.api_key_env)).complete(
            messages, tools
        )
        output = _response(message=result.model_dump(mode="json", exclude_defaults=True))
    except (
        CurationAuthenticationError,
        CurationResponseError,
        CurationTimeoutError,
        CurationTransportError,
    ) as error:
        output = _response(error=_error_code(error), detail=str(error))
    except (TypeError, ValueError, json.JSONDecodeError):
        output = _response(error="response")
    if len(output) > MAX_RESPONSE_BYTES:
        output = _response(error="response")
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
