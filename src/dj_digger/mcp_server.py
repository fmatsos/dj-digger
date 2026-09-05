"""MCP server exposing bounded DJ Digger curation reads and one normalized write."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dj_digger.catalog.database import Database
from dj_digger.config import WorkspaceConfig
from dj_digger.curation import (
    CandidateDetailsV1,
    CandidateRef,
    CandidateSearchV1,
    CreateCurationDraft,
    CurationCatalog,
    CurationCatalogError,
    CurationCreation,
    CurationKind,
    CurationRepository,
    CurationTrack,
    LibraryOverviewV1,
    SearchFilters,
)


def create_curation_mcp_server(config: WorkspaceConfig) -> MCPServer:
    """Create the catalog server with a single normalized curation write tool."""
    catalog = CurationCatalog(config.database)
    server = MCPServer(
        "DJ Digger Curation",
        instructions=(
            "Catalog V10 curation. create_curation is the only write tool and the required "
            "path for creating sets or playlists."
        ),
    )

    @server.tool(structured_output=True)
    async def get_library_overview() -> LibraryOverviewV1:
        try:
            return catalog.overview()
        except CurationCatalogError as error:
            raise ToolError(f"CURATION_ERROR: {error}") from None

    @server.tool(structured_output=True)
    async def search_curation_candidates(
        filters: SearchFilters | None = None,
        limit: int = 25,
        cursor: str | None = None,
    ) -> CandidateSearchV1:
        try:
            return catalog.search(filters or SearchFilters(), limit=limit, cursor=cursor)
        except CurationCatalogError as error:
            raise ToolError(f"CURATION_ERROR: {error}") from None

    @server.tool(structured_output=True)
    async def get_curation_candidates(candidates: list[CandidateRef]) -> CandidateDetailsV1:
        try:
            return catalog.get_candidates(candidates)
        except CurationCatalogError as error:
            raise ToolError(f"CURATION_ERROR: {error}") from None

    @server.tool(structured_output=True)
    async def create_curation(
        name: str,
        kind: CurationKind,
        user_prompt: str,
        report_markdown: str,
        tracks: list[CandidateRef],
    ) -> CurationCreation:
        """Atomically create one draft from an ordered list of available catalog tracks."""
        try:
            if not tracks:
                raise CurationCatalogError("a curation must contain at least one track")
            resolved = catalog.get_candidates(tracks)
            canonical = tuple(candidate.identity.track_id for candidate in resolved.candidates)
            draft = CreateCurationDraft(
                id=str(uuid4()),
                name=name,
                kind=kind,
                user_prompt=user_prompt,
                report_markdown=report_markdown,
                model_config_data={"model": config.curation.model},
                tracks=tuple(
                    CurationTrack(track_id=track_id, position=position)
                    for position, track_id in enumerate(canonical, start=1)
                ),
            )
            with Database.open(config.database) as database:
                return CurationRepository(database).create_draft(draft)
        except (CurationCatalogError, ValueError, sqlite3.Error) as error:
            raise ToolError(f"CURATION_ERROR: {error}") from None

    return server
