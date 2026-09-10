"""Typed refresh orchestration for one catalog publication."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dj_digger.core.analysis.config import (
    DEFAULT_TRACK_TIMEOUT_SECONDS,
    AnalysisIdentity,
)
from dj_digger.core.analysis.pipeline import (
    AnalysisExtractor,
    AnalysisRunResult,
    TimedAnalysisExtractor,
)
from dj_digger.core.application.analyze import AnalyzeRequest, AnalyzeUseCase
from dj_digger.core.application.export import ExportRequest, ExportResult, ExportUseCase
from dj_digger.core.application.metadata import MetadataRequest, MetadataRunResult, MetadataUseCase
from dj_digger.core.application.scan import ScanRequest, ScanRunResult, ScanUseCase
from dj_digger.core.catalog.database import Database
from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.progress import (
    NullProgressReporter,
    ProgressEventReporter,
    ProgressReporter,
    ProgressSink,
)


@dataclass(frozen=True)
class RefreshRequest:
    """Bounds for one complete scan-to-publication refresh."""

    workers: int = 1
    track_timeout: float = DEFAULT_TRACK_TIMEOUT_SECONDS


@dataclass(frozen=True)
class RefreshResult(Mapping[str, Any]):
    """Typed phase results with a compatibility mapping view.

    The mapping view is intentionally kept at the core boundary so callers of
    the historical application facade continue to receive the exact refresh
    payload while new callers can inspect each typed phase directly.
    """

    scans: ScanRunResult
    metadata: MetadataRunResult | None
    analysis: AnalysisRunResult | None
    exports: ExportResult | Sequence[str | Path] | None
    status: str
    published: bool
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event": "refresh",
            "status": self.status,
            "published": self.published,
            "scans": [_scan_dict(result) for result in self.scans.sources],
        }
        if self.error is not None:
            payload["error"] = self.error
        if self.metadata is not None:
            payload["metadata"] = _phase_dict(self.metadata)
        if self.analysis is not None:
            payload["analysis"] = _phase_dict(self.analysis)
        if self.exports is not None:
            paths = self.exports.paths if isinstance(self.exports, ExportResult) else self.exports
            payload["exports"] = [str(path) for path in paths]
        return payload

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.as_dict())

    def __len__(self) -> int:
        return len(self.as_dict())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return self.as_dict() == dict(other)
        if isinstance(other, RefreshResult):
            return (
                self.scans == other.scans
                and self.metadata == other.metadata
                and self.analysis == other.analysis
                and self.exports == other.exports
                and self.status == other.status
                and self.published == other.published
                and self.error == other.error
            )
        return NotImplemented


class RefreshUseCase:
    """Compose the focused core use cases without involving CLI parsing."""

    def __init__(
        self,
        database: Database,
        config: WorkspaceConfig,
        identity: AnalysisIdentity,
        extractor: AnalysisExtractor | TimedAnalysisExtractor,
        *,
        scan: Callable[[ScanRequest], ScanRunResult] | None = None,
        metadata: Callable[[MetadataRequest], MetadataRunResult] | None = None,
        analyze: Callable[[AnalyzeRequest, ProgressReporter | ProgressSink], AnalysisRunResult]
        | None = None,
        export: Callable[[ExportRequest], ExportResult | Sequence[str | Path]] | None = None,
    ) -> None:
        self._database = database
        self._config = config
        self._identity = identity
        self._extractor = extractor
        self._scan = scan
        self._metadata = metadata
        self._analyze = analyze
        self._export = export

    def execute(
        self,
        request: RefreshRequest | None = None,
        *,
        progress: ProgressReporter | ProgressSink | None = None,
    ) -> RefreshResult:
        request = request or RefreshRequest()
        if progress is None:
            reporter: ProgressReporter = NullProgressReporter()
        elif callable(progress):
            reporter = ProgressEventReporter(progress)
        else:
            reporter = progress
        reporter.phase_started("scan", 0, 4)
        scan_request = ScanRequest(enabled_only=True)
        scans = (
            self._scan(scan_request)
            if self._scan is not None
            else ScanUseCase(self._database, self._config).execute(scan_request)
        )
        reporter.phase_finished("scan", 1, 4)

        eligible = {source.id for source in self._config.sources if source.set_eligible}
        if any(not result.succeeded and result.source_id in eligible for result in scans.sources):
            return RefreshResult(scans, None, None, None, "failed", False)

        reporter.phase_started("metadata", 1, 4)
        metadata_request = MetadataRequest()
        metadata = (
            self._metadata(metadata_request)
            if self._metadata is not None
            else MetadataUseCase(self._database).execute(metadata_request)
        )
        reporter.phase_finished("metadata", 2, 4)

        reporter.phase_started("analysis", 2, 4)
        analyze_request = AnalyzeRequest(
            workers=request.workers, track_timeout=request.track_timeout
        )
        analysis = (
            self._analyze(analyze_request, reporter)
            if self._analyze is not None
            else AnalyzeUseCase(self._database, self._identity, self._extractor).execute(
                analyze_request, progress=reporter
            )
        )
        reporter.phase_finished("analysis", 3, 4)

        status = worst_status(
            "succeeded" if all(result.succeeded for result in scans.sources) else "partial",
            metadata.status,
            analysis.status,
        )
        reporter.phase_started("exports", 3, 4)
        try:
            export_request = ExportRequest()
            exports = (
                self._export(export_request)
                if self._export is not None
                else ExportUseCase(self._database, self._config).execute(export_request)
            )
        except Exception as error:
            reporter.phase_finished("exports", 4, 4)
            return RefreshResult(scans, metadata, analysis, None, "failed", False, str(error))
        reporter.phase_finished("exports", 4, 4)
        return RefreshResult(scans, metadata, analysis, exports, status, True)


def worst_status(*statuses: str) -> str:
    """Return the most severe refresh status in deterministic order."""

    order = {"succeeded": 0, "partial": 1, "failed": 2}
    return max(statuses, key=lambda status: order.get(status, 2))


def _phase_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "__dict__"):
        return dict(vars(result))
    return {
        name: getattr(result, name)
        for name in ("run_id", "eligible", "analyzed", "reused", "failed", "status")
        if hasattr(result, name)
    }


def _scan_dict(result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_id": result.source_id,
        "succeeded": result.succeeded,
    }
    run_id = getattr(result, "run_id", None)
    error = getattr(result, "error", None)
    if run_id is not None or error is not None:
        payload["run_id"] = run_id
        payload["error"] = error
    return payload


__all__ = ["RefreshRequest", "RefreshResult", "RefreshUseCase", "worst_status"]
