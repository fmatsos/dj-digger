"""Runtime composition helpers for CLI commands."""

import json
import tomllib
from pathlib import Path
from typing import Any

import typer

from dj_digger.cli.presenters.metadata import metadata_payload
from dj_digger.cli.presenters.refresh import refresh_payload
from dj_digger.cli.presenters.scan import scan_payload
from dj_digger.core.application import CoreApplication, MetadataRequest, RefreshRequest, ScanRequest
from dj_digger.core.application.progress import ProgressSink
from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.run_log import RunLogger


class ConfigLoadError(ValueError):
    """A workspace configuration could not be parsed or validated."""


def load_config(config_path: Path) -> WorkspaceConfig:
    """Load one workspace config with a stable, actionable CLI error."""
    try:
        return WorkspaceConfig.load(config_path)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as error:
        detail = str(error).strip() or "configuration is invalid"
        raise ConfigLoadError(f"invalid configuration: {detail}") from None


def config_failure(event: str, error: ConfigLoadError) -> dict[str, Any]:
    return {"event": event, "status": "failed", "code": "invalid_config", "error": str(error)}


def run_scan(config_path: Path, source_id: str | None) -> dict[str, Any]:
    """Run the core scan use case and return its compact diagnostic payload."""
    try:
        config = load_config(config_path)
    except ConfigLoadError as error:
        return config_failure("scan", error)
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
    try:
        config = load_config(config_path)
    except ConfigLoadError as error:
        return config_failure("metadata", error)
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


def run_refresh(
    config_path: Path,
    request: RefreshRequest | None = None,
    *,
    progress: ProgressSink | None = None,
) -> dict[str, Any]:
    """Run the typed refresh use case and return its compact payload."""

    try:
        config = load_config(config_path)
    except ConfigLoadError as error:
        return config_failure("refresh", error)
    logger = RunLogger(config.database)
    try:
        with CoreApplication(config) as service:
            diagnostic = refresh_payload(service.refresh(request, progress=progress))
    except Exception as error:
        diagnostic = {"event": "refresh", "status": "failed", "error": str(error)}
    logger.write(diagnostic)
    return diagnostic


def emit_json(payload: dict[str, Any]) -> None:
    """Emit one compact machine-readable payload."""
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
