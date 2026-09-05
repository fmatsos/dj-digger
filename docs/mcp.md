# Curation MCP (current)

DJ Digger exposes a deliberately small, read-only Model Context Protocol (MCP)
surface over Catalog V9. It is intended for local external agents and for the
future native curator. It never writes the catalog, reads source audio, or
accepts SQL.

## Start the server

Prepare the catalog with the normal workflow first (`refresh`, duplicate
fingerprinting, and quality/mastering analysis when needed). The server refuses
missing, empty, or non-V9 catalogs.

```bash
uv run dj-digger mcp --config /path/to/config.toml
dj-digger mcp --config /path/to/config.toml
uvx dj-digger mcp --config /path/to/config.toml
```

The process uses MCP stdio only. Do not configure a host, port, token, HTTP
endpoint, SSE endpoint, or remote bind address.

## Tools

Exactly three tools are published:

* `get_library_overview` returns bounded counts, source IDs, freshness timestamps,
  analysis status coverage, quality status coverage, and deterministic facets.
* `search_curation_candidates` accepts a `SearchFilters` object, `limit` (1-50),
  and an opaque cursor. Text searches title, artist, album, grouping, comment,
  filename, and source-relative path across eligible duplicate members; numeric
  filters apply to the selected representative.
* `get_curation_candidates` accepts 1-20 unique `{source_id, track_id}` references
  from search and preserves request order.

Results use contract version `curation/v1`. Candidate identity is the exact
`(source_id, track_id, path)` tuple, with a source-relative path. Duplicate
representatives are ranked lossless first, then bit depth/sample rate or lossy
bitrate/sample rate, then source/path/id. Quality is `unique`, `verified_best`,
`best_effort`, or `unverified_unfingerprinted`.

The newest analysis attempt is authoritative. A failed or stale attempt is
reported as uncertain and does not fall back to older BPM, key, sections, or
windows. Missing values are JSON `null`.

## Privacy boundary

Responses contain only identity, discovery metadata, audio format/quality,
allowlisted analysis facts, intro/outro windows, section summaries, and current
mastering/DJ values. They never contain source roots, absolute paths, database or
export paths, file size/mtime, hashes or fingerprints, analyzer/config versions,
raw JSON payloads, SQL, tracebacks, or per-track failure messages.

## Agent configuration

Configure local clients with a command and argument array. For example, the
tested shape for Claude Code is:

```json
{
  "mcpServers": {
    "dj-digger-curation": {
      "type": "stdio",
      "command": "uvx",
      "args": ["dj-digger", "mcp", "--config", "/path/to/config.toml"]
    }
  }
}
```

Codex clients use the same local stdio command/argument shape in their MCP
server configuration. Keep the config and database on the local machine.
Client configuration keys can evolve independently; the command remains the
public contract.

The next native-agent tranche will use the same factory in memory:

```python
from mcp import Client
from dj_digger.mcp_server import create_curation_mcp_server

server = create_curation_mcp_server(workspace_config)
async with Client(server) as client:
    overview = await client.call_tool("get_library_overview", {})
```

This does not implement the native agent loop, provider, transition evaluator,
draft validation, persistence, or set emission.

## Troubleshooting

* Missing or empty database: run `refresh` with the same config.
* Unsupported catalog version: migrate or recreate through the normal catalog
  workflow; MCP never migrates a database.
* `missing` analysis: run `analyze` for the eligible source.
* `unverified_unfingerprinted`: fingerprint the library; the track remains a
  candidate because absence of a fingerprint is uncertainty, not exclusion.
* `best_effort`: complete technical facts are missing for at least one known
  duplicate member; curate with that uncertainty visible.
