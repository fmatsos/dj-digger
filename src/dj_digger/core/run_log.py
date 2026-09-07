"""Run diagnostics written outside music-library source roots."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s,;\"']+)")
_SAFE_ERROR_CLASSES = (
    "authentication",
    "dependency unavailable",
    "invalid response",
    "state conflict",
    "stale",
    "timeout",
    "unavailable",
)


def sanitize_error(error: object) -> str:
    """Map arbitrary exception detail to a safe, stable failure class."""
    message = str(error).lower()
    for classification in _SAFE_ERROR_CLASSES:
        if classification in message:
            return classification
    return "operation failed"


def sanitize_diagnostic(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Remove private paths and arbitrary exception detail from persisted facts."""

    def sanitize_value(key: str, value: Any) -> Any:
        if key == "error":
            return sanitize_error(value)
        if isinstance(value, dict):
            return {
                str(child_key): sanitize_value(str(child_key), child)
                for child_key, child in value.items()
            }
        if isinstance(value, list):
            return [sanitize_value(key, child) for child in value]
        if isinstance(value, tuple):
            return [sanitize_value(key, child) for child in value]
        if isinstance(value, str):
            return _ABSOLUTE_PATH.sub("<path>", value)
        return value

    return {str(key): sanitize_value(str(key), value) for key, value in diagnostic.items()}


class RunLogger:
    """Append concise, human-readable command diagnostics to the workspace log."""

    def __init__(self, database_path: Path) -> None:
        self._path = database_path.parent / "logs" / "dj-digger.log"

    def write(self, diagnostic: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).isoformat()
        event = diagnostic.get("event", "command")
        status = diagnostic.get("status", "unknown")
        safe_diagnostic = sanitize_diagnostic(diagnostic)
        details = json.dumps(safe_diagnostic, ensure_ascii=False, sort_keys=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {event} {status} {details}\n")


__all__ = ["RunLogger", "sanitize_diagnostic", "sanitize_error"]
