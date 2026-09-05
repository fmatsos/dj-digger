from pathlib import Path

import anyio

from dj_digger.catalog.database import Database
from dj_digger.config import WorkspaceConfig
from dj_digger.mcp_server import create_curation_mcp_server


def _config(path: Path) -> WorkspaceConfig:
    with Database.open(path) as database:
        database.migrate()
        database.execute(
            "INSERT INTO library_sources VALUES ('source', '/fixture', 1, 1, 1, 'now', 'now', NULL)"
        )
        database.execute(
            "INSERT INTO scan_runs (id, source_id, started_at, status, scanner_version) "
            "VALUES (1, 'source', 'now', 'succeeded', 'test')"
        )
        database.execute(
            """INSERT INTO tracks VALUES
            (1, 'source', 'item.flac', 'item.flac', '.flac', 1, 1, 'present',
             'now', 'now', NULL, NULL, 1, 1)"""
        )
        database.commit()
    return WorkspaceConfig(database=path, exports=path.parent / "exports", sources=())


def test_in_process_server_exposes_one_normalized_write_tool(tmp_path: Path) -> None:
    server = create_curation_mcp_server(_config(tmp_path / "catalog.sqlite"))

    async def exercise() -> None:
        from mcp import Client

        async with Client(server) as client:
            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == [
                "get_library_overview",
                "search_curation_candidates",
                "get_curation_candidates",
                "create_curation",
            ]
            result = await client.call_tool("get_library_overview", {})
            assert result.structured_content["contract_version"] == "curation/v1"
            created = await client.call_tool(
                "create_curation",
                {
                    "name": "Draft",
                    "kind": "set",
                    "user_prompt": "Build a set",
                    "report_markdown": "# Report",
                    "tracks": [{"source_id": "source", "track_id": 1}],
                },
            )
            assert created.structured_content["status"] == "draft"
            assert created.structured_content["tracks"] == [{"track_id": 1, "position": 1}]
            assert (await client.list_resources()).resources == []
            assert (await client.list_prompts()).prompts == []

    anyio.run(exercise)
