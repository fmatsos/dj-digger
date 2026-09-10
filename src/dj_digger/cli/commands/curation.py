"""CLI adapters for catalog-grounded curation workflows."""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from dj_digger.cli.presenters.curation import creation_payload, curation_error, emit_curation
from dj_digger.core.application import CoreApplication
from dj_digger.core.application.curation import CurationRequest
from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.curation import CurationStatus
from dj_digger.core.errors import classify
from dj_digger.core.exports.curation import CurationExportContent
from dj_digger.core.run_log import RunLogger

curation_app = typer.Typer(help="Create, inspect, and validate catalog-grounded curations.")


def _default_config_path() -> Path:
    workspace = Path.cwd()
    candidates = (
        workspace / "config.toml",
        workspace / "config" / "config.toml",
        Path.home() / ".dj-digger" / "config.toml",
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.R_OK):
            return candidate.resolve()
    raise typer.BadParameter(
        "no configuration file found; pass --config PATH or create "
        "config.toml, config/config.toml, or ~/.dj-digger/config.toml"
    )


ConfigOption = Annotated[
    Path,
    typer.Option(
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        default_factory=_default_config_path,
        show_default=False,
        help="Workspace config; discovered automatically when omitted.",
    ),
]
JsonOption = Annotated[
    bool, typer.Option("--json", help="Emit the compact machine-readable JSON payload.")
]


def _run_curation(
    config_path: Path,
    action: Callable[[CoreApplication], dict[str, Any]],
    *,
    json_output: bool,
) -> None:
    try:
        config = WorkspaceConfig.load(config_path)
    except Exception as error:
        typer.echo(f"Error: {curation_error(error)}", err=True)
        raise typer.Exit(1) from None
    try:
        with CoreApplication(config) as service:
            payload = action(service)
    except Exception as error:
        message = curation_error(error)
        RunLogger(config.database).write(
            {
                "event": "curation",
                "status": "failed",
                "error": message,
                "error_class": classify(error),
            }
        )
        typer.echo(f"Error: {message}", err=True)
        raise typer.Exit(1) from None
    emit_curation(payload, json_output=json_output)


@curation_app.command("create")
def curation_create(
    config: ConfigOption,
    prompt: Annotated[str | None, typer.Argument(help="Direct curation prompt.")] = None,
    prompt_file: Annotated[
        Path | None,
        typer.Option("--prompt-file", exists=True, file_okay=True, dir_okay=False, readable=True),
    ] = None,
    kind: Annotated[Literal["set", "playlist"], typer.Option("--kind")] = "set",
    name: Annotated[str | None, typer.Option("--name")] = None,
    max_tracks: Annotated[int, typer.Option("--max-tracks", min=1, max=20)] = 10,
    json_output: JsonOption = False,
) -> None:
    """Run the curation agent and atomically save its grounded result as a draft."""
    if (prompt is None) == (prompt_file is None):
        raise typer.BadParameter("provide exactly one of PROMPT or --prompt-file")
    try:
        if prompt is not None:
            text = prompt
        elif prompt_file is not None:
            text = prompt_file.read_text(encoding="utf-8")
        else:
            raise ValueError("missing prompt")
    except (OSError, UnicodeError):
        typer.echo("Error: Prompt file is unreadable UTF-8; fix the file and retry.", err=True)
        raise typer.Exit(1) from None

    workspace: WorkspaceConfig | None = None
    try:
        workspace = WorkspaceConfig.load(config)
        with CoreApplication(workspace) as service:
            result = asyncio.run(
                service.create_curation(
                    CurationRequest(prompt=text, kind=kind, name=name, max_tracks=max_tracks)
                )
            )
    except Exception as error:
        message = curation_error(error)
        if workspace is not None:
            with contextlib.suppress(OSError):
                RunLogger(workspace.database).write(
                    {
                        "event": "curation",
                        "status": "failed",
                        "error": message,
                        "error_class": classify(error),
                    }
                )
        typer.echo(f"Error: {message}", err=True)
        raise typer.Exit(1) from None
    emit_curation(creation_payload(result.creation), json_output=json_output)


@curation_app.command("show")
def curation_show(
    creation_id: Annotated[str, typer.Argument(metavar="ID")],
    config: ConfigOption,
    json_output: JsonOption = False,
) -> None:
    """Show sanitized metadata, ordered tracks, status, and Markdown report."""

    def action(service: CoreApplication) -> dict[str, Any]:
        creation = service.get_curation(creation_id)
        if creation is None:
            raise ValueError("unknown curation ID")
        return creation_payload(creation)

    _run_curation(config, action, json_output=json_output)


@curation_app.command("list")
def curation_list(
    config: ConfigOption,
    status: Annotated[CurationStatus | None, typer.Option("--status")] = None,
    json_output: JsonOption = False,
) -> None:
    """List curations, optionally filtered by lifecycle status."""

    def action(service: CoreApplication) -> dict[str, Any]:
        return {
            "name": "curations",
            "id": "list",
            "kind": "collection",
            "status": status or "all",
            "tracks": [],
            "curations": [
                creation_payload(creation, include_report=False)
                for creation in service.list_curations(status)
            ],
        }

    _run_curation(config, action, json_output=json_output)


@curation_app.command("validate")
def curation_validate(
    creation_id: Annotated[str, typer.Argument(metavar="ID")],
    config: ConfigOption,
    json_output: JsonOption = False,
) -> None:
    """Explicitly transition a reviewed draft to validated."""
    _run_curation(
        config,
        lambda service: creation_payload(service.validate_curation(creation_id)),
        json_output=json_output,
    )


@curation_app.command("export")
def curation_export(
    creation_id: Annotated[str, typer.Argument(metavar="ID")],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    config: ConfigOption,
    content: Annotated[CurationExportContent, typer.Option("--content")] = "both",
    copy_files: Annotated[
        bool,
        typer.Option(
            "--copy-files",
            help="Copy tracks for a portable export; required for multi-source playlists.",
        ),
    ] = False,
) -> None:
    """Export a report and/or M3U8; multi-source playlists require copied files."""
    try:
        workspace = WorkspaceConfig.load(config)
        with CoreApplication(workspace) as service:
            result = service.export_curation(
                creation_id, content=content, copy_files=copy_files, output=output
            )
    except Exception as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Exported {result.track_count} tracks to {result.output}")


__all__ = ["curation_app"]
