"""Run diagnostics written outside music-library source roots."""

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dj_digger.core.errors import UNCLASSIFIED, classify

# Absolute filesystem paths are private library facts; URLs are configuration
# the operator needs to read back, so they are matched first and preserved.
_URL = r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s,;\"']+"
_ABSOLUTE_PATH = r"(?<![A-Za-z0-9_:/])/(?:[^\s,;\"']+)"
_SCRUBBED = re.compile(f"(?P<url>{_URL})|(?P<path>{_ABSOLUTE_PATH})")
_FILE_URL = re.compile(r"(?i)\bfile:///(?:[^\s,;\"']+)")


def _scrub_paths(value: str) -> str:
    without_file_paths = _FILE_URL.sub("file://<path>", value)
    return _SCRUBBED.sub(lambda match: match.group("url") or "<path>", without_file_paths)


def sanitize_error(error: object) -> str:
    """Map arbitrary exception detail to a safe, stable failure class.

    Classification comes from the exception type, so rewording a message never
    silently changes what a run log reports, and an unexpected exception can
    never leak private library detail into persisted facts.
    """
    return classify(error)


def sanitize_diagnostic(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    """Remove private paths and arbitrary exception detail from persisted facts.

    A boundary that caught a real exception records its failure class under
    ``error_class``; that classification is reused here because the ``error``
    field is already a message string by the time it reaches persistence.
    Without it the message is dropped entirely rather than guessed at.
    """
    declared = diagnostic.get("error_class")
    top_level_class = declared if isinstance(declared, str) else UNCLASSIFIED

    def sanitize_value(key: str, value: Any) -> Any:
        if key == "error":
            if value is None:
                return None
            return top_level_class if isinstance(value, str) else sanitize_error(value)
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
            return _scrub_paths(value)
        return value

    return {str(key): sanitize_value(str(key), value) for key, value in diagnostic.items()}


class RunLogger:
    """Append concise, human-readable command diagnostics to the workspace log."""

    def __init__(self, database_path: Path) -> None:
        self._path = database_path.parent / "logs" / "dj-digger.log"

    def write(self, diagnostic: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).isoformat()
        event = diagnostic.get("event", "command")
        status = diagnostic.get("status", "unknown")
        safe_diagnostic = sanitize_diagnostic(diagnostic)
        details = json.dumps(safe_diagnostic, ensure_ascii=False, sort_keys=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {event} {status} {details}\n")


__all__ = ["RunLogger", "sanitize_diagnostic", "sanitize_error"]
