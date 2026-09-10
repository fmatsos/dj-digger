"""Typed application contracts for duplicate workflows."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dj_digger.core.analysis.config import DEFAULT_TRACK_TIMEOUT_SECONDS
from dj_digger.core.catalog.database import Database
from dj_digger.core.config import MasteringConfig
from dj_digger.core.duplicates.quality import QualityMarkResult
from dj_digger.core.duplicates.service import (
    DuplicateAnalysisResult,
    DuplicateGroupDescription,
    DuplicateService,
)
from dj_digger.core.progress import ProgressReporter


@dataclass(frozen=True)
class DuplicateAnalyzeRequest:
    """Scope and safety limits for one duplicate fingerprint pass."""

    source_id: str | None = None
    workers: int = 1
    track_timeout: float = DEFAULT_TRACK_TIMEOUT_SECONDS
    mark_best_quality: bool = False
    mastering: bool = False


@dataclass(frozen=True)
class DuplicateListRequest:
    """Scope for one duplicate group listing."""

    source_id: str | None = None


@dataclass(frozen=True)
class DuplicateMarkBestRequest:
    """Scope for one standalone duplicate quality selection."""

    source_id: str | None = None


class DuplicateAnalyzeUseCase:
    """Execute one duplicate analysis request against the canonical service."""

    def __init__(
        self,
        database: Database,
        source_roots: Mapping[str, Path],
        *,
        mastering_config: MasteringConfig,
    ) -> None:
        self._database = database
        self._source_roots = source_roots
        self._mastering_config = mastering_config

    def execute(
        self,
        request: DuplicateAnalyzeRequest,
        *,
        progress: ProgressReporter | None = None,
    ) -> DuplicateAnalysisResult:
        return DuplicateService(
            self._database,
            self._source_roots,
            progress=progress,
            mastering_config=self._mastering_config,
        ).analyze(
            source_id=request.source_id,
            workers=request.workers,
            track_timeout=request.track_timeout,
            mark_best_quality=request.mark_best_quality,
            mastering=request.mastering,
        )


class DuplicateListUseCase:
    """Return duplicate groups enriched with canonical facts and quality state."""

    def __init__(
        self,
        database: Database,
        source_roots: Mapping[str, Path],
        *,
        mastering_config: MasteringConfig,
    ) -> None:
        self._database = database
        self._source_roots = source_roots
        self._mastering_config = mastering_config

    def execute(self, request: DuplicateListRequest) -> list[DuplicateGroupDescription]:
        return DuplicateService(
            self._database,
            self._source_roots,
            mastering_config=self._mastering_config,
        ).describe_groups(request.source_id)


class DuplicateMarkBestUseCase:
    """Persist the canonical best-quality selection for duplicate groups."""

    def __init__(
        self,
        database: Database,
        source_roots: Mapping[str, Path],
        *,
        mastering_config: MasteringConfig,
    ) -> None:
        self._database = database
        self._source_roots = source_roots
        self._mastering_config = mastering_config

    def execute(self, request: DuplicateMarkBestRequest) -> QualityMarkResult:
        return DuplicateService(
            self._database,
            self._source_roots,
            mastering_config=self._mastering_config,
        ).mark_best_quality(request.source_id)


__all__ = [
    "DuplicateAnalysisResult",
    "DuplicateAnalyzeRequest",
    "DuplicateAnalyzeUseCase",
    "DuplicateGroupDescription",
    "DuplicateListRequest",
    "DuplicateListUseCase",
    "DuplicateMarkBestRequest",
    "DuplicateMarkBestUseCase",
    "QualityMarkResult",
]
