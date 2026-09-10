"""The catalog-tool port the curation agent orchestrates.

The agent needs exactly two capabilities from whatever exposes the catalog as
tools. Naming them here keeps the agent in the domain: the MCP server is an
inbound adapter and is wired in by the composition root, not imported from
inside the domain.
"""

from typing import Any, Protocol

ALLOWED_TOOLS = (
    "get_library_overview",
    "search_curation_candidates",
    "get_curation_candidates",
    "create_curation",
)
WRITE_TOOL = "create_curation"


class CatalogTool(Protocol):
    """One tool the model may call."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str | None: ...

    @property
    def input_schema(self) -> dict[str, Any]: ...


class CatalogToolServer(Protocol):
    """Expose bounded catalog tools to the curation agent."""

    async def list_tools(self) -> list[Any]: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


__all__ = ["ALLOWED_TOOLS", "WRITE_TOOL", "CatalogTool", "CatalogToolServer"]
