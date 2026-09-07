"""Strict HTTP client for OpenAI-compatible chat completions."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dj_digger.core.config import CurationConfig

__all__ = [
    "CurationClientError",
    "CurationAuthenticationError",
    "CurationTimeoutError",
    "CurationTransportError",
    "CurationResponseError",
    "ToolCall",
    "AssistantMessage",
    "OpenAICompatibleClient",
    "complete_in_subprocess",
    "CompletionClient",
]


class CurationClientError(RuntimeError):
    """Sanitized base error for the remote model boundary."""


class CurationAuthenticationError(CurationClientError):
    """The configured environment variable has no usable credential."""


class CurationTimeoutError(CurationClientError):
    """The bounded model request timed out."""


class CurationTransportError(CurationClientError):
    """The model endpoint could not return a successful response."""


class CurationResponseError(CurationClientError):
    """The model endpoint returned a malformed response."""


class _FunctionCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1)
    arguments: str


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1)
    type: str
    function: _FunctionCall


class AssistantMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: str
    content: str | None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class CompletionClient(Protocol):
    """Explicit synchronous seam for injected curation completions."""

    def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
    ) -> AssistantMessage: ...


class _Choice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    index: int
    message: AssistantMessage
    finish_reason: str | None


class _Completion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    choices: list[_Choice] = Field(min_length=1, max_length=1)


class OpenAICompatibleClient:
    """Send bounded JSON requests without ever retaining or reporting the secret."""

    def __init__(self, config: CurationConfig, api_key: str | None) -> None:
        self._config = config
        if api_key is None or not api_key.strip():
            raise CurationAuthenticationError(
                f"curation credential is missing from {config.api_key_env}"
            )
        self._api_key = api_key

    def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
    ) -> AssistantMessage:
        if self._config.endpoint == "responses":
            payload_value = _responses_payload(self._config, messages, tools)
        else:
            payload_value = {
                "model": self._config.model,
                "messages": list(messages),
                "tools": list(tools),
                "tool_choice": "auto",
                "max_completion_tokens": self._config.max_output_tokens,
                "reasoning_effort": self._config.reasoning_effort,
            }
        payload = json.dumps(
            payload_value,
            separators=(",", ":"),
        ).encode()
        request = urllib.request.Request(
            f"{self._config.base_url}/{self._config.endpoint}",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._config.request_timeout_seconds
            ) as response:
                raw = response.read(self._config.max_output_tokens * 16 + 1)
        except TimeoutError:
            raise CurationTimeoutError("curation model request timed out") from None
        except urllib.error.HTTPError as error:
            if error.code in {401, 403}:
                raise CurationAuthenticationError(
                    "curation model rejected the configured credential"
                ) from None
            detail = _http_error_detail(error, self._api_key)
            raise CurationTransportError(detail) from None
        except (urllib.error.URLError, OSError):
            raise CurationTransportError("curation model request failed") from None
        if len(raw) > self._config.max_output_tokens * 16:
            raise CurationResponseError("curation model response exceeded its size limit")
        try:
            value = json.loads(raw)
            if self._config.endpoint == "responses":
                return _parse_responses_message(value)
            return _Completion.model_validate(value).choices[0].message
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError):
            raise CurationResponseError("curation model returned an invalid response") from None


async def complete_in_subprocess(
    client: OpenAICompatibleClient,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
    *,
    timeout: float,
) -> AssistantMessage:
    """Run one HTTP completion in a process that can be killed at the deadline."""
    request = json.dumps(
        {
            "protocol_version": 1,
            "config": asdict(client._config),
            "messages": list(messages),
            "tools": list(tools),
        },
        separators=(",", ":"),
    ).encode()
    if len(request) > 1_000_000:
        raise CurationResponseError("curation model request exceeded its size limit")
    environment = os.environ.copy()
    environment[client._config.api_key_env] = client._api_key
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "dj_digger.core.curation.client_worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
        )
    except OSError:
        raise CurationTransportError("curation model process could not start") from None
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(request), timeout=timeout)
    except TimeoutError:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise CurationTimeoutError("curation model request timed out") from None
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    if process.returncode != 0 or len(stdout) > 1_000_000:
        raise CurationTransportError("curation model process failed")
    try:
        value = json.loads(stdout)
        if (
            not isinstance(value, dict)
            or value.get("protocol_version") != 1
            or not isinstance(value.get("ok"), bool)
        ):
            raise ValueError
        if not value["ok"]:
            error = value.get("error")
            if error == "authentication":
                raise CurationAuthenticationError(
                    "curation model rejected the configured credential"
                )
            if error == "timeout":
                raise CurationTimeoutError("curation model request timed out")
            if error == "response":
                raise CurationResponseError("curation model returned an invalid response")
            detail = value.get("detail")
            if not isinstance(detail, str) or not detail:
                detail = "curation model request failed"
            raise CurationTransportError(detail)
        message = value.get("message")
        if not isinstance(message, dict):
            raise ValueError
        return AssistantMessage.model_validate(message)
    except (
        CurationAuthenticationError,
        CurationResponseError,
        CurationTimeoutError,
        CurationTransportError,
    ):
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, ValidationError):
        raise CurationResponseError("curation model returned an invalid response") from None


def _http_error_detail(error: urllib.error.HTTPError, api_key: str) -> str:
    """Return a bounded provider error without ever exposing the credential."""
    raw = error.read(16_384)
    message = ""
    try:
        value = json.loads(raw)
        provider_error = value.get("error") if isinstance(value, dict) else None
        if isinstance(provider_error, dict) and isinstance(provider_error.get("message"), str):
            message = " ".join(provider_error["message"].split())
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    message = message.replace(api_key, "[REDACTED]")[:2_000]
    suffix = f": {message}" if message else ""
    return f"HTTP {error.code}{suffix}"


def _responses_payload(
    config: CurationConfig,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    input_items: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "assistant":
            content = message.get("content")
            if isinstance(content, str) and content:
                input_items.append({"role": "assistant", "content": content})
            tool_calls = message.get("tool_calls", [])
            if isinstance(tool_calls, list):
                for call in tool_calls:
                    if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                        continue
                    function = call["function"]
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": call.get("id"),
                            "name": function.get("name"),
                            "arguments": function.get("arguments"),
                        }
                    )
        elif role == "tool":
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id"),
                    "output": message.get("content"),
                }
            )
        else:
            input_items.append(dict(message))
    response_tools = []
    for tool in tools:
        function = tool.get("function")
        if isinstance(function, Mapping):
            response_tools.append({"type": "function", **function})
    return {
        "model": config.model,
        "input": input_items,
        "tools": response_tools,
        "tool_choice": "auto",
        "max_output_tokens": config.max_output_tokens,
        "reasoning": {"effort": config.reasoning_effort},
        "store": False,
    }


def _parse_responses_message(value: object) -> AssistantMessage:
    if not isinstance(value, dict) or not isinstance(value.get("output"), list):
        raise TypeError
    content_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for item in value["output"]:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "function_call":
            tool_calls.append(
                ToolCall.model_validate(
                    {
                        "id": item.get("call_id"),
                        "type": "function",
                        "function": {"name": item.get("name"), "arguments": item.get("arguments")},
                    }
                )
            )
        elif item.get("type") == "message" and isinstance(item.get("content"), list):
            for content in item["content"]:
                if (
                    isinstance(content, dict)
                    and content.get("type") == "output_text"
                    and isinstance(content.get("text"), str)
                ):
                    content_parts.append(content["text"])
    return AssistantMessage(
        role="assistant",
        content="\n".join(content_parts) or None,
        tool_calls=tool_calls,
    )
