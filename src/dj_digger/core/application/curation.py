"""Typed application boundary for catalog-grounded curation."""

from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.curation.agent import (
    CuratedTrack,
    CurationAgent,
    CurationAgentError,
    CurationGroundingError,
    CurationMCPError,
    CurationRequest,
    CurationResult,
    CurationTurnLimitError,
)
from dj_digger.core.curation.client import (
    CurationAuthenticationError,
    CurationClientError,
    CurationResponseError,
    CurationTimeoutError,
    CurationTransportError,
)


class CurationUseCase:
    """Run one asynchronous, bounded curation request against the core catalog."""

    def __init__(self, config: WorkspaceConfig) -> None:
        self._config = config

    async def execute(self, request: CurationRequest) -> CurationResult:
        return await CurationAgent(self._config).run(request)


__all__ = [
    "CurationAgent",
    "CurationAgentError",
    "CurationAuthenticationError",
    "CurationClientError",
    "CurationGroundingError",
    "CurationMCPError",
    "CurationRequest",
    "CurationResponseError",
    "CurationResult",
    "CurationTimeoutError",
    "CurationTransportError",
    "CurationTurnLimitError",
    "CuratedTrack",
    "CurationUseCase",
]
