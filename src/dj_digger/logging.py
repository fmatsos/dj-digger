"""Run diagnostics written outside music-library source roots."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class RunLogger:
    """Append concise, human-readable command diagnostics to the workspace log."""

    def __init__(self, database_path: Path) -> None:
        self._path = database_path.parent / "logs" / "dj-digger.log"

    def write(self, diagnostic: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).isoformat()
        event = diagnostic.get("event", "command")
        status = diagnostic.get("status", "unknown")
        details = json.dumps(diagnostic, ensure_ascii=False, sort_keys=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {event} {status} {details}\n")
