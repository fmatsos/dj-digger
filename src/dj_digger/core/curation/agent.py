"""Bounded, catalog-grounded curation agent orchestration."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, cast

from mcp.types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from dj_digger.core.catalog.database import Database
from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.curation.catalog import CurationCatalog, CurationCatalogError
from dj_digger.core.curation.client import (
    CompletionClient,
    CurationClientError,
    CurationResponseError,
    OpenAICompatibleClient,
    complete_in_subprocess,
)
from dj_digger.core.curation.models import CandidateDetails, CandidateRef, CurationCreation
from dj_digger.core.curation.prompts import CUSTOM_SYSTEM_PROMPT_PREFIX, SYSTEM_PROMPT
from dj_digger.core.curation.tools import ALLOWED_TOOLS, WRITE_TOOL, CatalogToolServer
from dj_digger.core.errors import StateConflictError

__all__ = [
    "ALLOWED_TOOLS",
    "WRITE_TOOL",
    "CuratedTrack",
    "CurationAgent",
    "CurationAgentError",
    "CurationGroundingError",
    "CurationMCPError",
    "CurationRequest",
    "CurationResult",
    "CurationTurnLimitError",
]


class CurationAgentError(StateConflictError):
    """Sanitized, typed orchestration failure."""


class CurationTurnLimitError(CurationAgentError):
    """The model did not finish within its configured turn budget."""

    classification = "timeout"


class CurationMCPError(CurationAgentError):
    """The local MCP composition or tool execution failed."""

    classification = "unavailable"


class CurationGroundingError(CurationAgentError):
    """The result was not grounded in currently available catalog candidates."""

    classification = "stale"


class CurationRequest(BaseModel):
    """Strict bounded user request."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    prompt: str = Field(min_length=1, max_length=4_000)
    custom_system_prompt: str | None = Field(default=None, min_length=1, max_length=4_000)
    max_tracks: int = Field(default=10, ge=1, le=20)
    kind: str = Field(default="set", pattern="^(set|playlist)$")
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def reject_blank(self) -> CurationRequest:
        if not self.prompt.strip():
            raise ValueError("prompt must not be blank")
        if self.custom_system_prompt is not None and not self.custom_system_prompt.strip():
            raise ValueError("custom_system_prompt must not be blank")
        return self


class CuratedTrack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    rationale: str
    catalog: CandidateDetails


class CurationResult(BaseModel):
    """Final result whose factual fields are rebuilt from the catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    creation: CurationCreation
    tracks: tuple[CuratedTrack, ...]


class CurationAgent:
    """Run grounded curation with a terminable default transport.

    The default ``OpenAICompatibleClient`` runs in a fresh subprocess and is
    hard-terminated at the aggregate deadline. An explicitly injected
    ``CompletionClient`` is called through its synchronous seam in a worker
    thread for test/custom integration; cancellation is bounded, but arbitrary
    injected code is not claimed to be hard-killable.
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        client: CompletionClient | None = None,
        *,
        tool_server: CatalogToolServer,
    ) -> None:
        self._config = config
        self._catalog = CurationCatalog(config.database)
        self._server = tool_server
        self._uses_default_transport = client is None
        self._client: CompletionClient = (
            client
            if client is not None
            else OpenAICompatibleClient(
                config.curation, os.environ.get(config.curation.api_key_env)
            )
        )

    async def run(self, request: CurationRequest) -> CurationResult:
        if request.max_tracks > self._config.curation.max_output_tracks:
            raise CurationGroundingError(
                "requested track count exceeds the configured output limit"
            )
        available_tools = [
            tool for tool in await self._server.list_tools() if tool.name in ALLOWED_TOOLS
        ]
        if tuple(tool.name for tool in available_tools) != ALLOWED_TOOLS:
            raise CurationMCPError("curation tool composition is invalid")
        tool_defs: list[dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "DJ Digger catalog query",
                    "parameters": tool.input_schema,
                },
            }
            for tool in available_tools
        ]
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if request.custom_system_prompt is not None:
            messages.append(
                {
                    "role": "system",
                    "content": CUSTOM_SYSTEM_PROMPT_PREFIX + request.custom_system_prompt.strip(),
                }
            )
        messages.append(
            {
                "role": "user",
                "content": f"Select at most {request.max_tracks} tracks. {request.prompt.strip()}",
            }
        )
        deadline = asyncio.get_running_loop().time() + self._config.curation.total_timeout_seconds
        try:
            async with asyncio.timeout(self._config.curation.total_timeout_seconds):
                for _turn in range(self._config.curation.max_turns):
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise CurationTurnLimitError("curation agent exceeded its total timeout")
                    if self._uses_default_transport:
                        response = await complete_in_subprocess(
                            cast(OpenAICompatibleClient, self._client),
                            messages,
                            tool_defs,
                            timeout=remaining,
                        )
                    else:
                        response = await asyncio.wait_for(
                            asyncio.to_thread(self._client.complete, messages, tool_defs),
                            timeout=remaining,
                        )
                    assistant = response.model_dump(mode="json", exclude_defaults=True)
                    messages.append(assistant)
                    if response.tool_calls:
                        for call in response.tool_calls:
                            if call.type != "function" or call.function.name not in ALLOWED_TOOLS:
                                raise CurationGroundingError("model requested a forbidden tool")
                            try:
                                arguments = json.loads(call.function.arguments)
                            except (json.JSONDecodeError, TypeError):
                                raise CurationResponseError(
                                    "curation model returned invalid tool arguments"
                                ) from None
                            if not isinstance(arguments, dict):
                                raise CurationResponseError(
                                    "curation model returned invalid tool arguments"
                                )
                            if call.function.name == WRITE_TOOL:
                                if len(response.tool_calls) != 1:
                                    raise CurationGroundingError(
                                        "creation write must be the only tool call in its turn"
                                    )
                                tracks = arguments.get("tracks")
                                if isinstance(tracks, list) and len(tracks) > request.max_tracks:
                                    raise CurationGroundingError(
                                        "curation result has an invalid track count"
                                    )
                                arguments["user_prompt"] = request.prompt.strip()
                                arguments["kind"] = request.kind
                                if request.name is not None:
                                    arguments["name"] = request.name.strip()
                            try:
                                result = await self._server.call_tool(call.function.name, arguments)
                            except CurationCatalogError as error:
                                message = str(error).lower()
                                if call.function.name == WRITE_TOOL and any(
                                    word in message
                                    for word in ("unknown", "unavailable", "candidate")
                                ):
                                    raise CurationGroundingError(
                                        "curation result references an unknown or unavailable track"
                                    ) from None
                                raise CurationMCPError(str(error)) from None
                            except Exception as error:
                                message = str(error).lower()
                                if call.function.name == WRITE_TOOL and any(
                                    word in message
                                    for word in ("unknown", "unavailable", "candidate")
                                ):
                                    raise CurationGroundingError(
                                        "curation result references an unknown or unavailable track"
                                    ) from None
                                raise CurationMCPError("catalog tool call failed") from None
                            if not isinstance(result, CallToolResult):
                                raise CurationMCPError("catalog tool requested user input")
                            if result.is_error or result.structured_content is None:
                                raise CurationMCPError("catalog tool call failed")
                            if call.function.name == WRITE_TOOL:
                                return self._ground_creation(
                                    result.structured_content, request.max_tracks
                                )
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call.id,
                                    "content": json.dumps(
                                        result.structured_content, separators=(",", ":")
                                    ),
                                }
                            )
                        continue
                    raise CurationGroundingError(
                        "curation model must create its result with create_curation"
                    )
        except TimeoutError:
            raise CurationTurnLimitError("curation agent exceeded its total timeout") from None
        except CurationClientError:
            raise
        raise CurationTurnLimitError("curation agent exceeded its maximum number of turns")

    def _ground_creation(self, content: dict[str, Any], max_tracks: int) -> CurationResult:
        try:
            creation = CurationCreation.model_validate(content)
        except ValidationError:
            raise CurationResponseError("curation tool returned an invalid creation") from None
        if not 1 <= len(creation.tracks) <= max_tracks:
            raise CurationGroundingError("curation result has an invalid track count")
        with Database.open_read_only(self._config.database) as database:
            source_by_track = {
                int(track_id): str(source_id)
                for track_id, source_id in database.execute(
                    "SELECT id, source_id FROM tracks WHERE id IN ({})".format(
                        ",".join("?" for _ in creation.tracks)
                    ),
                    tuple(track.track_id for track in creation.tracks),
                )
            }
        refs = [
            CandidateRef(source_id=source_by_track[track.track_id], track_id=track.track_id)
            for track in creation.tracks
        ]
        try:
            resolved = self._catalog.get_candidates(refs)
        except CurationCatalogError:
            raise CurationGroundingError(
                "curation result references an unknown or unavailable track"
            ) from None
        return CurationResult(
            creation=creation,
            tracks=tuple(
                CuratedTrack(rationale="Persisted in curation report.", catalog=details)
                for details in resolved.candidates
            ),
        )
