"""Compatibility re-exports for the canonical curation client."""

from dj_digger.core.curation.client import (
    AssistantMessage,
    CompletionClient,
    CurationAuthenticationError,
    CurationClientError,
    CurationResponseError,
    CurationTimeoutError,
    CurationTransportError,
    OpenAICompatibleClient,
    ToolCall,
    complete_in_subprocess,
)

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
