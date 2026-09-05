"""MCP server exposing the bounded DJ Digger curation read model."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dj_digger.config import WorkspaceConfig
from dj_digger.curation import (
    CandidateDetailsV1,
    CandidateRef,
    CandidateSearchV1,
    CurationCatalog,
    CurationCatalogError,
    LibraryOverviewV1,
    SearchFilters,
)


def create_curation_mcp_server(config: WorkspaceConfig) -> MCPServer:
    """Create the same read-only server used by native and external clients."""
    catalog = CurationCatalog(config.database)
    server = MCPServer(
        "DJ Digger Curation",
        instructions="Read-only Catalog V9 discovery and curation candidates.",
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

    return server
