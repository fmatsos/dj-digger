"""Typed application boundary for bounded audio analysis."""

from dataclasses import dataclass

from dj_digger.core.analysis.config import (
    DEFAULT_TRACK_TIMEOUT_SECONDS,
    AnalysisIdentity,
)
from dj_digger.core.analysis.pipeline import (
    AnalysisExtractor,
    AnalysisPipeline,
    AnalysisRunResult,
    TimedAnalysisExtractor,
)
from dj_digger.core.catalog.database import Database
from dj_digger.core.progress import (
    AnalysisProgressReporter,
    NullProgressReporter,
    ProgressEventReporter,
    ProgressSink,
)


@dataclass(frozen=True)
class AnalyzeRequest:
    """Scope and safety limits for one analysis run."""

    source_id: str | None = None
    path_prefix: str | None = None
    limit: int | None = None
    force: bool = False
    workers: int = 1
    track_timeout: float = DEFAULT_TRACK_TIMEOUT_SECONDS


class AnalyzeUseCase:
    """Delegate one typed request to the real parent-owned analysis pipeline."""

    def __init__(
        self,
        database: Database,
        identity: AnalysisIdentity,
        extractor: AnalysisExtractor | TimedAnalysisExtractor,
    ) -> None:
        self._database = database
        self._identity = identity
        self._extractor = extractor

    def execute(
        self,
        request: AnalyzeRequest,
        *,
        progress: ProgressSink | AnalysisProgressReporter | None = None,
    ) -> AnalysisRunResult:
        reporter = _progress_reporter(progress)
        return AnalysisPipeline(
            self._database,
            self._identity,
            self._extractor,
            progress=reporter,
        ).run(
            source_id=request.source_id,
            path_prefix=request.path_prefix,
            limit=request.limit,
            force=request.force,
            workers=request.workers,
            track_timeout=request.track_timeout,
        )


def _progress_reporter(
    progress: ProgressSink | AnalysisProgressReporter | None,
) -> AnalysisProgressReporter:
    if progress is None:
        return NullProgressReporter()
    if callable(progress):
        return ProgressEventReporter(progress)
    return progress


__all__ = ["AnalysisRunResult", "AnalyzeRequest", "AnalyzeUseCase"]
