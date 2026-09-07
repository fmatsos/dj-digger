"""CLI adapter for the bounded curation MCP stdio server."""

from pathlib import Path
from typing import Annotated

import typer

from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.curation import CurationCatalog
from dj_digger.core.mcp_server import create_curation_mcp_server

ConfigOption = Annotated[
    Path,
    typer.Option(
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        show_default=False,
        help="Workspace config.",
    ),
]


def serve(config: Path) -> None:
    """Serve bounded curation reads and draft creation over MCP stdio."""
    try:
        workspace = WorkspaceConfig.load(config)
        CurationCatalog(workspace.database).overview()
        create_curation_mcp_server(workspace).run(transport="stdio")
    except Exception as error:
        typer.echo(f"MCP startup failed: {error}", err=True)
        raise typer.Exit(1) from None


__all__ = ["serve"]
