"""Runtime composition helpers for CLI commands."""

import json
from pathlib import Path
from typing import Any

import typer

from dj_digger.cli.presenters.metadata import metadata_payload
from dj_digger.cli.presenters.scan import scan_payload
from dj_digger.core.application import CoreApplication, MetadataRequest, ScanRequest
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


def run_metadata(
    config_path: Path,
    source_id: str | None,
    path_prefix: str | None,
    force: bool,
) -> dict[str, Any]:
    """Run the core metadata use case and return its compact payload."""
    config = WorkspaceConfig.load(config_path)
    logger = RunLogger(config.database)
    try:
        with CoreApplication(config) as service:
            diagnostic = metadata_payload(
                service.metadata(
                    MetadataRequest(source_id=source_id, path_prefix=path_prefix, force=force)
                )
            )
    except Exception as error:
        diagnostic = {"event": "metadata", "status": "failed", "error": str(error)}
    logger.write(diagnostic)
    return diagnostic


def emit_json(payload: dict[str, Any]) -> None:
    """Emit one compact machine-readable payload."""
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
