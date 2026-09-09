"""Presentation mapping for curation commands."""

from typing import Any

import typer

from dj_digger.cli.runtime import emit_json
from dj_digger.core.curation.models import CurationCreation


def creation_payload(creation: CurationCreation, *, include_report: bool = True) -> dict[str, Any]:
    """Return the historical sanitized curation JSON shape."""
    payload: dict[str, Any] = {
        "id": creation.id,
        "name": creation.name,
        "kind": creation.kind,
        "status": creation.status,
        "created_at": creation.created_at,
        "updated_at": creation.updated_at,
        "validated_at": creation.validated_at,
        "model": creation.model_config_data,
        "tracks": [track.model_dump(mode="json") for track in creation.tracks],
    }
    if include_report:
        payload["report_markdown"] = creation.report_markdown
    return payload


def emit_curation(payload: dict[str, Any], *, json_output: bool) -> None:
    """Emit one curation payload in JSON or the historical text format."""
    if json_output:
        emit_json(payload)
        return
    typer.echo(f"{payload['name']} ({payload['id']})")
    typer.echo(f"kind: {payload['kind']}")
    typer.echo(f"status: {payload['status']}")
    tracks = payload.get("tracks", [])
    typer.echo("tracks: " + ", ".join(str(track["track_id"]) for track in tracks))
    for creation in payload.get("curations", []):
        typer.echo(
            f"{creation['id']}  {creation['status']}  {creation['kind']}  {creation['name']}"
        )
    if "report_markdown" in payload:
        typer.echo("report:")
        typer.echo(str(payload["report_markdown"]))


def curation_error(error: Exception) -> str:
    """Map core curation failures to the stable CLI wording."""
    from dj_digger.core.application.curation import (
        CurationAuthenticationError,
        CurationGroundingError,
        CurationMCPError,
        CurationResponseError,
        CurationTimeoutError,
        CurationTransportError,
        CurationTurnLimitError,
    )

    if isinstance(error, CurationAuthenticationError):
        return "Remote authentication failed; check the configured credential environment variable."
    if isinstance(error, (CurationTimeoutError, CurationTurnLimitError)):
        return "Curation timed out; retry or increase the configured timeout."
    if isinstance(error, CurationResponseError):
        return "The model returned an invalid response; verify model compatibility and retry."
    if isinstance(error, CurationTransportError):
        return f"The model request failed: {error}"
    if isinstance(error, CurationMCPError):
        return f"The catalog tool failed: {error}"
    if isinstance(error, CurationGroundingError):
        return "A selected track reference is stale or unavailable; refresh the catalog and retry."
    if isinstance(error, RuntimeError):
        return "Curation state conflict; reload the curation before retrying."
    if isinstance(error, (OSError, ValueError)):
        return "Invalid curation configuration or input; check paths, options, and config values."
    return "Curation failed safely; check the workspace database and retry."


__all__ = ["creation_payload", "curation_error", "emit_curation"]
