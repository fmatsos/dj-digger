"""Runtime composition helpers for CLI commands."""

import json
from pathlib import Path
from typing import Any

import typer

from dj_digger.cli.presenters.scan import scan_payload
from dj_digger.core.application import CoreApplication, ScanRequest
from dj_digger.core.config import WorkspaceConfig
from dj_digger.logging import RunLogger


def run_scan(config_path: Path, source_id: str | None) -> dict[str, Any]:
    """Run the core scan use case and return its compact diagnostic payload."""
    config = WorkspaceConfig.load(config_path)
    logger = RunLogger(config.database)
    try:
        with CoreApplication(config) as service:
            diagnostic = scan_payload(service.scan(ScanRequest(source_id=source_id)))
    except Exception as error:
        diagnostic = {"event": "scan", "status": "failed", "error": str(error)}
    logger.write(diagnostic)
    return diagnostic


def emit_json(payload: dict[str, Any]) -> None:
    """Emit one compact machine-readable payload."""
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
