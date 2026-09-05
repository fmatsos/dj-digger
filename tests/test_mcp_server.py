from pathlib import Path

import anyio

from dj_digger.catalog.database import Database
from dj_digger.config import WorkspaceConfig
from dj_digger.mcp_server import create_curation_mcp_server


def _config(path: Path) -> WorkspaceConfig:
    with Database.open(path) as database:
        database.migrate()
    return WorkspaceConfig(database=path, exports=path.parent / "exports", sources=())


def test_in_process_server_exposes_only_typed_read_tools(tmp_path: Path) -> None:
    server = create_curation_mcp_server(_config(tmp_path / "catalog.sqlite"))

    async def exercise() -> None:
        from mcp import Client

        async with Client(server) as client:
            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == [
                "get_library_overview",
                "search_curation_candidates",
                "get_curation_candidates",
            ]
            result = await client.call_tool("get_library_overview", {})
            assert result.structured_content["contract_version"] == "curation/v1"
            assert (await client.list_resources()).resources == []
            assert (await client.list_prompts()).prompts == []

    anyio.run(exercise)
