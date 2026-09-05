"""Strict HTTP client for OpenAI-compatible chat completions."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dj_digger.config import CurationConfig


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
        payload = json.dumps(
            {
                "model": self._config.model,
                "messages": list(messages),
                "tools": list(tools),
                "tool_choice": "auto",
                "max_tokens": self._config.max_output_tokens,
            },
            separators=(",", ":"),
        ).encode()
        request = urllib.request.Request(
            f"{self._config.base_url}/chat/completions",
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
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            raise CurationTransportError("curation model request failed") from None
        if len(raw) > self._config.max_output_tokens * 16:
            raise CurationResponseError("curation model response exceeded its size limit")
        try:
            value = json.loads(raw)
            return _Completion.model_validate(value).choices[0].message
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError):
            raise CurationResponseError("curation model returned an invalid response") from None
