# Native curation

> Current user documentation for the implemented `dj-digger curation` commands.

DJ Digger includes a bounded curation agent. It combines the CLI, an
OpenAI-compatible chat-completions endpoint, the in-memory MCP tool surface, the
catalog-backed curation repository, and the atomic exporter. The model has no direct
database, music-library, or filesystem access.

## Trust order and grounding

The trust order is strict:

1. **DJ Digger identities and facts are authoritative.** Availability, source and
   track IDs, source-relative paths, metadata, quality, and analysis come only from
   current MCP catalog results.
2. **General LLM knowledge is advisory only.** It may inform search strategy,
   sequencing ideas, and explanations, but it cannot override or supplement catalog
   facts.
3. **A track absent from the catalog results cannot be selected or persisted.** The
   agent must inspect every selection, and the write tool resolves every reference
   again before atomically creating a draft.

Prompt text and optional personality instructions are untrusted preferences. They
cannot weaken this order, enable other tools, or turn an invented title into a track.

## Endpoint and credential configuration

Add a `[curation]` table to the workspace configuration. This example uses only
fictional labels and container-neutral relative locations:

```toml
[workspace]
database = "../demo-workspace/catalog.sqlite"
exports = "../demo-workspace/exports"

[curation]
base_url = "https://models.example.invalid/v1"
endpoint = "chat/completions"
model = "aurora-selector-demo"
reasoning_effort = "none"
api_key_env = "DJ_DIGGER_CURATION_CREDENTIAL"
request_timeout_seconds = 30
total_timeout_seconds = 120
max_turns = 8
max_output_tokens = 2000
max_output_tracks = 20
```

`base_url` is the HTTP(S) API root. `endpoint` accepts `chat/completions` (the
default) or `responses`; a leading slash is optional. The legacy `/completions`
resource is not supported because it cannot run the required function tools.
`reasoning_effort` defaults to `none` and accepts `none`, `minimal`, `low`, `medium`,
`high`, `xhigh`, or `max`; support still depends on the selected model and endpoint.
`model` is passed unchanged to that API. Configure the
*name* of the credential variable with `api_key_env`, then inject its value only into
the command environment:

```console
DJ_DIGGER_CURATION_CREDENTIAL="<injected-by-your-secret-manager>" \
  dj-digger curation create --config config/demo.toml \
  "Build a compact sunrise set from the fictional Neon Archive collection"
```

Do not put a credential value in TOML, prompts, shell history, or committed examples.
Configuration keys named `api_key`, `key`, `token`, or `secret` are rejected. A
missing or blank configured environment variable fails before a model request.

## What is sent to the model

Each HTTPS request contains:

- the configured model name;
- the immutable grounding system prompt and, when supplied by an API caller, a
  subordinate custom style prompt;
- the user's curation brief and requested maximum track count;
- OpenAI function definitions for the four MCP tools;
- prior assistant tool calls and the sanitized structured results returned by those
  tools during this run;
- `tool_choice: auto`, the configured reasoning effort, and the configured
  output-token limit.

Tool results may include source IDs, track IDs, source-relative paths, discovery
metadata (including artist and title), audio format and quality, current analysis,
sections, transition windows, mastering facts, counts, facets, and freshness. They do
not include source roots, absolute paths, database/export paths, file size or mtime,
fingerprints/hashes, raw analyzer payloads, SQL, tracebacks, or credentials. Library
metadata is nevertheless private: use an endpoint and retention policy appropriate
for that data.

## Bounds and unavailable services

- `request_timeout_seconds` bounds each endpoint request.
- `total_timeout_seconds` bounds the whole agent run and must be at least the request
  timeout.
- `max_turns` bounds model round trips (supported range: 1–32).
- `max_output_tokens` bounds each response (supported range: 1–100,000); an additional
  response-byte limit rejects oversized bodies.
- `max_output_tracks` is the workspace ceiling (supported range: 1–20), while CLI
  `--max-tracks` requests an equal or smaller result.

Authentication rejection, transport failure, request or total timeout, invalid JSON
or tool arguments, forbidden tools, turn exhaustion, catalog/tool failure, and stale
track references all fail closed with a sanitized CLI error and exit code `1`. No
fallback model is used, no ungrounded draft is stored, and no partial export is
published. Correct the credential or endpoint and retry; increase limits deliberately
only when the service is healthy. If catalog identities are stale, run `refresh` and
create a new draft.

## Draft, review, validation, and status filtering

Create from one direct prompt or one UTF-8 prompt file (never both):

```console
dj-digger curation create --config config/demo.toml --kind set \
  --name "Neon Observatory" --max-tracks 12 \
  "Build a fictional late-night arc with a gentle landing"
dj-digger curation create --config config/demo.toml --kind playlist \
  --prompt-file examples/fictional-brief.txt
```

A successful agent run always persists a `draft`; the model cannot mark it validated.
Review the saved order and report, list all creations, or filter by lifecycle status:

```console
dj-digger curation show CURATION_ID --config config/demo.toml
dj-digger curation list --config config/demo.toml
dj-digger curation list --status draft --config config/demo.toml
dj-digger curation list --status validated --config config/demo.toml
```

After human review, validation is an explicit, one-way, idempotent transition:

```console
dj-digger curation validate CURATION_ID --config config/demo.toml
```

`create`, `show`, `list`, and `validate` accept `--json`. There is no edit or
`validated` → `draft` transition: create a new draft when the selection must change.

## Export variants and multi-source playlists

Both `draft` and `validated` creations can be exported:

```console
dj-digger curation export CURATION_ID --config config/demo.toml \
  --content report --output demo-exports/review
dj-digger curation export CURATION_ID --config config/demo.toml \
  --content playlist --output demo-exports/player
dj-digger curation export CURATION_ID --config config/demo.toml \
  --content both --copy-files --output demo-exports/portable-set
```

`report` writes `report.md`; `playlist` writes `curation.m3u8`; `both` writes both.
`--copy-files` additionally copies ordered tracks beneath `tracks/` and makes playlist
entries relative. Without copying, playlist entries resolve to source files and every
track must belong to one configured source. A multi-source playlist is refused unless
`--copy-files` is used; report-only export is unaffected. The output directory must
not already exist, and publication is atomic.

See [Curation exports](curation-export.md) for filesystem validation details and
[Curation MCP](mcp.md) for the tool contract.
