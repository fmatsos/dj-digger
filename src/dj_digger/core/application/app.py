"""Application-level orchestration for the DJ Digger command line."""

import importlib.util
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast, overload

from dj_digger.core.analysis.config import CURRENT_ANALYZER_VERSION, AnalysisIdentity
from dj_digger.core.analysis.pipeline import (
    AnalysisExtractor,
    AnalysisRunResult,
    TimedAnalysisExtractor,
)
from dj_digger.core.analysis.worker_client import IsolatedAnalysisExtractor
from dj_digger.core.application.analysis_progress import NullProgressReporter, ProgressReporter
from dj_digger.core.application.analyze import AnalyzeRequest, AnalyzeUseCase
from dj_digger.core.application.curation import CurationRequest, CurationResult, CurationUseCase
from dj_digger.core.application.duplicates import (
    DuplicateAnalyzeRequest,
    DuplicateAnalyzeUseCase,
    DuplicateListRequest,
    DuplicateListUseCase,
    DuplicateMarkBestRequest,
    DuplicateMarkBestUseCase,
)
from dj_digger.core.application.errors import InvalidInputError, ResourceNotFoundError
from dj_digger.core.application.export import ExportRequest, ExportResult, ExportUseCase
from dj_digger.core.application.metadata import (
    MetadataRequest,
    MetadataRunResult,
    MetadataUseCase,
)
from dj_digger.core.application.operations import (
    DatabaseIntegrityCheckResult,
    DatabaseOptimizeResult,
    DatabaseQuickCheckResult,
    DatabaseRebuildResult,
    DoctorResult,
    DoctorUseCase,
    IntegrityCheckDatabaseUseCase,
    OptimizeDatabaseUseCase,
    QuickCheckDatabaseUseCase,
    RebuildCurrentAnalysisUseCase,
    StatusResult,
    StatusUseCase,
    has_chromaprint_muxer,
)
from dj_digger.core.application.progress import ProgressSink
from dj_digger.core.application.scan import ScanRequest, ScanRunResult, ScanUseCase
from dj_digger.core.application.snapshot import SnapshotRequest, SnapshotResult, SnapshotUseCase
from dj_digger.core.catalog.database import Database
from dj_digger.core.catalog.repositories import SourceRepository
from dj_digger.core.config import LibrarySourceConfig, WorkspaceConfig
from dj_digger.core.curation.models import CurationCreation, CurationStatus
from dj_digger.core.curation.repository import CurationRepository
from dj_digger.core.duplicates.quality import QualityMarkResult
from dj_digger.core.duplicates.service import (
    DuplicateAnalysisResult,
    DuplicateGroupDescription,
    DuplicateService,
)
from dj_digger.core.exports.curation import (
    CurationExportContent,
    CurationExportResult,
    export_curation,
)


@dataclass(frozen=True)
class ScanResult:
    source_id: str
    succeeded: bool
    run_id: int | None
    error: str | None = None


class WorkspaceApplication:
    """Coordinate catalog scanning, metadata, analysis, and publication."""

    def __init__(
        self, config: WorkspaceConfig, *, analysis_extractor: AnalysisExtractor | None = None
    ) -> None:
        self.config = config
        database = Database.open(config.database)
        self.database = database
        try:
            database.migrate()
            self._sources = SourceRepository(database)
            self._analysis_extractor: AnalysisExtractor | TimedAnalysisExtractor
            if analysis_extractor is None:
                self._analysis_identity = AnalysisIdentity(
                    2, CURRENT_ANALYZER_VERSION, config.dsp.config_hash
                )
                self._analysis_extractor = IsolatedAnalysisExtractor(
                    {source.id: source.path for source in config.sources}, config.dsp
                )
            else:
                self._analysis_extractor = analysis_extractor
                self._analysis_identity = getattr(
                    analysis_extractor,
                    "identity",
                    AnalysisIdentity(2, CURRENT_ANALYZER_VERSION, config.dsp.config_hash),
                )
            with database.transaction():
                for source in config.sources:
                    self._sources.upsert(
                        source.id,
                        source.path,
                        set_eligible=source.set_eligible,
                        analyze=source.analyze,
                        enabled=source.enabled,
                    )
        except BaseException:
            database.close()
            raise

    def close(self) -> None:
        """Close the application-owned catalog connection."""
        self.database.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def scan(self, source_id: str | None = None, *, enabled_only: bool = False) -> list[ScanResult]:
        """Run the legacy scan contract retained for existing Python callers."""
        request = ScanRequest(source_id=source_id, enabled_only=enabled_only)
        return _legacy_scan_results(self._scan_result(request))

    def _scan_result(self, request: ScanRequest) -> ScanRunResult:
        """Execute one canonical scan orchestration for all application facades."""
        return ScanUseCase(self.database, self.config).execute(request)

    def _scan_for_refresh(self, *, enabled_only: bool) -> list[ScanResult]:
        """Adapt the legacy scan result required by the refresh composition."""
        return self.scan(enabled_only=enabled_only)

    def metadata(
        self,
        source_id: str | MetadataRequest | None = None,
        *,
        path_prefix: str | None = None,
        force: bool = False,
    ) -> MetadataRunResult:
        request = (
            source_id
            if isinstance(source_id, MetadataRequest)
            else MetadataRequest(source_id=source_id, path_prefix=path_prefix, force=force)
        )
        return self._metadata_result(request)

    def _metadata_result(self, request: MetadataRequest) -> MetadataRunResult:
        """Execute one canonical metadata orchestration for all facades."""
        return MetadataUseCase(self.database).execute(request)

    def analyze(
        self,
        request: AnalyzeRequest | str | None = None,
        *,
        source_id: str | None = None,
        path_prefix: str | None = None,
        limit: int | None = None,
        force: bool = False,
        workers: int = 1,
        track_timeout: float = 1800.0,
        progress: ProgressReporter | None = None,
    ) -> AnalysisRunResult:
        """Run the configured injectable audio analysis extractor."""
        effective = (
            request
            if isinstance(request, AnalyzeRequest)
            else AnalyzeRequest(
                source_id=request if isinstance(request, str) else source_id,
                path_prefix=path_prefix,
                limit=limit,
                force=force,
                workers=workers,
                track_timeout=track_timeout,
            )
        )
        return self._analyze_request(effective, progress=progress)

    def _analyze_request(
        self,
        request: AnalyzeRequest,
        *,
        progress: ProgressReporter | ProgressSink | None = None,
    ) -> AnalysisRunResult:
        if request.source_id is not None:
            self._selected_sources(request.source_id, enabled_only=True)
        return AnalyzeUseCase(
            self.database, self._analysis_identity, self._analysis_extractor
        ).execute(request, progress=progress)

    def duplicates_analyze(
        self,
        request: DuplicateAnalyzeRequest | str | None = None,
        *,
        source_id: str | None = None,
        workers: int = 1,
        track_timeout: float = 1800.0,
        mark_best_quality: bool = False,
        mastering: bool = False,
        progress: ProgressReporter | None = None,
    ) -> DuplicateAnalysisResult:
        """Run duplicate analysis through the typed core request contract."""
        if isinstance(request, DuplicateAnalyzeRequest):
            effective = replace(request, source_id=_legacy_source(request.source_id, source_id))
        else:
            effective = DuplicateAnalyzeRequest(
                source_id=_legacy_source(request, source_id),
                workers=workers,
                track_timeout=track_timeout,
                mark_best_quality=mark_best_quality,
                mastering=mastering,
            )
        return self._duplicate_analyze_request(effective, progress=progress)

    def _duplicate_analyze_request(
        self,
        request: DuplicateAnalyzeRequest,
        *,
        progress: ProgressReporter | None = None,
    ) -> DuplicateAnalysisResult:
        self._require_duplicate_source(request.source_id)
        return DuplicateAnalyzeUseCase(
            self.database,
            {source.id: source.path for source in self.config.sources},
            mastering_config=self.config.mastering,
        ).execute(request, progress=progress)

    def duplicates_list(
        self,
        request: DuplicateListRequest | str | None = None,
        *,
        source_id: str | None = None,
    ) -> list[DuplicateGroupDescription]:
        """List duplicate groups through the typed core request contract."""
        effective = (
            replace(request, source_id=_legacy_source(request.source_id, source_id))
            if isinstance(request, DuplicateListRequest)
            else DuplicateListRequest(source_id=_legacy_source(request, source_id))
        )
        return self._duplicate_list_request(effective)

    def _duplicate_list_request(
        self, request: DuplicateListRequest
    ) -> list[DuplicateGroupDescription]:
        self._require_duplicate_source(request.source_id)
        return DuplicateListUseCase(
            self.database,
            {source.id: source.path for source in self.config.sources},
            mastering_config=self.config.mastering,
        ).execute(request)

    def duplicates_mark_best_quality(
        self,
        request: DuplicateMarkBestRequest | str | None = None,
        *,
        source_id: str | None = None,
    ) -> QualityMarkResult:
        """Mark the best-quality copy through the typed core request contract."""
        effective = (
            replace(request, source_id=_legacy_source(request.source_id, source_id))
            if isinstance(request, DuplicateMarkBestRequest)
            else DuplicateMarkBestRequest(source_id=_legacy_source(request, source_id))
        )
        return self._duplicate_mark_best_request(effective)

    def _duplicate_mark_best_request(self, request: DuplicateMarkBestRequest) -> QualityMarkResult:
        self._require_duplicate_source(request.source_id)
        return DuplicateMarkBestUseCase(
            self.database,
            {source.id: source.path for source in self.config.sources},
            mastering_config=self.config.mastering,
        ).execute(request)

    def _require_duplicate_source(self, source_id: str | None) -> None:
        if source_id is None:
            return
        try:
            self._selected_sources(source_id, enabled_only=True)
        except ValueError as error:
            raise ResourceNotFoundError(str(error)) from error

    async def create_curation(self, request: CurationRequest) -> CurationResult:
        """Run and persist one catalog-grounded draft asynchronously."""
        return await CurationUseCase(self.config).execute(request)

    def curation_get(self, creation_id: str) -> CurationCreation | None:
        """Return one durable curation."""
        return CurationRepository(self.database).get(creation_id)

    def curation_list(self, status: CurationStatus | None = None) -> tuple[CurationCreation, ...]:
        """List durable curations for CLI and future web consumers."""
        return CurationRepository(self.database).list(status)

    def curation_validate(self, creation_id: str) -> CurationCreation:
        """Explicitly transition a draft to validated."""
        creation = CurationRepository(self.database).get(creation_id)
        if creation is None:
            raise ValueError("unknown curation ID")
        if creation.status != "draft":
            raise RuntimeError("curation is already validated")
        return CurationRepository(self.database).validate(creation_id)

    def curation_export(
        self,
        creation_id: str,
        *,
        content: CurationExportContent,
        copy_files: bool,
        output: Path,
    ) -> CurationExportResult:
        """Publish a persisted curation from one consistent catalog snapshot."""
        return export_curation(
            self.database,
            self.config,
            creation_id,
            content=content,
            copy_files=copy_files,
            output=output,
        )

    def _duplicate_service(self, *, progress: ProgressReporter | None = None) -> DuplicateService:
        return DuplicateService(
            self.database,
            {source.id: source.path for source in self.config.sources},
            progress=progress,
            mastering_config=self.config.mastering,
        )

    @overload
    def export(
        self,
        facet: ExportRequest,
        *,
        type: str | None = None,
        format: str | None = None,
        fields: str | None = None,
    ) -> ExportResult: ...

    @overload
    def export(
        self,
        facet: str | None = None,
        *,
        type: str | None = None,
        format: str | None = None,
        fields: str | None = None,
    ) -> list[str]: ...

    def export(
        self,
        facet: str | ExportRequest | None = None,
        *,
        type: str | None = None,
        format: str | None = None,
        fields: str | None = None,
    ) -> ExportResult | list[str]:
        request = (
            facet
            if isinstance(facet, ExportRequest)
            else ExportRequest(facet=facet, type=type, format=format, fields=fields)
        )
        try:
            result = ExportUseCase(self.database, self.config).execute(request)
        except InvalidInputError as error:
            # Keep the historical facade's exception type stable. Core callers
            # use ExportUseCase/CoreApplication and receive InvalidInputError.
            raise ValueError(str(error)) from error
        if isinstance(facet, ExportRequest):
            return result
        return [str(path) for path in result.paths]

    def _legacy_export(self) -> list[str]:
        """Publish the historical all-facets result for refresh composition."""
        result = self.export()
        if isinstance(result, ExportResult):
            return [str(path) for path in result.paths]
        return result

    def snapshot(self, output: Path | SnapshotRequest, archive: bool = False) -> SnapshotResult:
        request = (
            output if isinstance(output, SnapshotRequest) else SnapshotRequest(output, archive)
        )
        return SnapshotUseCase(self.database).execute(request)

    def refresh(
        self,
        *,
        workers: int = 1,
        track_timeout: float = 1800.0,
        progress: ProgressReporter | None = None,
    ) -> dict[str, Any]:
        reporter = progress or NullProgressReporter()
        reporter.phase_started("scan", 0, 4)
        scans = self._scan_for_refresh(enabled_only=True)
        reporter.phase_finished("scan", 1, 4)
        eligible = {source.id for source in self.config.sources if source.set_eligible}
        required_failure = any(
            not result.succeeded and result.source_id in eligible for result in scans
        )
        if required_failure:
            return {
                "event": "refresh",
                "status": "failed",
                "published": False,
                "scans": [result.__dict__ for result in scans],
            }
        reporter.phase_started("metadata", 1, 4)
        metadata = self.metadata()
        reporter.phase_finished("metadata", 2, 4)
        reporter.phase_started("analysis", 2, 4)
        analysis = self.analyze(workers=workers, track_timeout=track_timeout, progress=reporter)
        reporter.phase_finished("analysis", 3, 4)
        status = _worst_status(
            "succeeded" if all(result.succeeded for result in scans) else "partial",
            metadata.status,
            analysis.status,
        )
        reporter.phase_started("exports", 3, 4)
        try:
            exports = self._legacy_export()
        except Exception as error:
            reporter.phase_finished("exports", 4, 4)
            return {
                "event": "refresh",
                "status": "failed",
                "published": False,
                "error": str(error),
                "scans": [result.__dict__ for result in scans],
                "metadata": metadata.__dict__,
                "analysis": analysis.__dict__,
            }
        reporter.phase_finished("exports", 4, 4)
        return {
            "event": "refresh",
            "status": status,
            "published": True,
            "scans": [result.__dict__ for result in scans],
            "metadata": metadata.__dict__,
            "analysis": analysis.__dict__,
            "exports": exports,
        }

    def status(self) -> dict[str, Any]:
        return StatusUseCase(self.database, self.config).execute().as_dict()

    def optimize_database(self) -> dict[str, Any]:
        """Run SQLite's bounded planner-statistics maintenance."""
        return OptimizeDatabaseUseCase(self.database).execute().as_dict()

    def quick_check_database(self) -> dict[str, Any]:
        """Run the lightweight SQLite consistency check explicitly."""
        return QuickCheckDatabaseUseCase(self.database).execute().as_dict()

    def integrity_check_database(self) -> dict[str, Any]:
        """Run SQLite's full integrity check explicitly."""
        return IntegrityCheckDatabaseUseCase(self.database).execute().as_dict()

    def rebuild_current_analysis(self) -> dict[str, Any]:
        """Rebuild the derived latest-success projection, then update planner statistics."""
        return RebuildCurrentAnalysisUseCase(self.database).execute().as_dict()

    def doctor(self) -> dict[str, Any]:
        return (
            DoctorUseCase(
                self.database,
                self.config,
                chromaprint_check=_has_chromaprint_muxer,
                which=shutil.which,
                find_spec=importlib.util.find_spec,
            )
            .execute()
            .as_dict()
        )

    def _selected_sources(
        self, source_id: str | None, *, enabled_only: bool
    ) -> tuple[LibrarySourceConfig, ...]:
        sources = tuple(
            source for source in self.config.sources if not enabled_only or source.enabled
        )
        if source_id is None:
            return sources
        selected = tuple(source for source in sources if source.id == source_id)
        if not selected:
            raise ValueError(f"unknown or disabled source: {source_id}")
        return selected


class CoreApplication(WorkspaceApplication):
    """Framework-independent application boundary for core use cases."""

    def __init__(
        self, config: WorkspaceConfig, *, analysis_extractor: object | None = None
    ) -> None:
        super().__init__(
            config,
            analysis_extractor=cast(AnalysisExtractor | None, analysis_extractor),
        )

    def status(self) -> StatusResult:  # type: ignore[override]
        """Return the typed workspace status contract."""
        return StatusUseCase(self.database, self.config).execute()

    def doctor(self) -> DoctorResult:  # type: ignore[override]
        """Return typed workspace and SQLite diagnostics."""
        return DoctorUseCase(
            self.database,
            self.config,
            chromaprint_check=_has_chromaprint_muxer,
            which=shutil.which,
            find_spec=importlib.util.find_spec,
        ).execute()

    def optimize_database(self) -> DatabaseOptimizeResult:  # type: ignore[override]
        return OptimizeDatabaseUseCase(self.database).execute()

    def quick_check_database(self) -> DatabaseQuickCheckResult:  # type: ignore[override]
        return QuickCheckDatabaseUseCase(self.database).execute()

    def integrity_check_database(self) -> DatabaseIntegrityCheckResult:  # type: ignore[override]
        return IntegrityCheckDatabaseUseCase(self.database).execute()

    def rebuild_current_analysis(self) -> DatabaseRebuildResult:  # type: ignore[override]
        return RebuildCurrentAnalysisUseCase(self.database).execute()

    def get_curation(self, creation_id: str) -> CurationCreation | None:
        """Return one durable curation through the typed core boundary."""
        return self.curation_get(creation_id)

    def list_curations(self, status: CurationStatus | None = None) -> tuple[CurationCreation, ...]:
        """List durable curations through the typed core boundary."""
        return self.curation_list(status)

    def validate_curation(self, creation_id: str) -> CurationCreation:
        """Transition one draft to validated through the typed core boundary."""
        return self.curation_validate(creation_id)

    def export_curation(
        self,
        creation_id: str,
        *,
        content: CurationExportContent,
        copy_files: bool,
        output: Path,
    ) -> CurationExportResult:
        """Publish one persisted curation through the typed core boundary."""
        return self.curation_export(
            creation_id, content=content, copy_files=copy_files, output=output
        )

    def scan(self, request: ScanRequest) -> ScanRunResult:  # type: ignore[override]
        """Scan the requested sources and return immutable typed results."""
        return self._scan_result(request)

    def metadata(self, request: MetadataRequest | None = None) -> MetadataRunResult:  # type: ignore[override]
        """Refresh metadata through the typed core contract."""
        return super().metadata(request or MetadataRequest())

    def analyze(
        self,
        request: AnalyzeRequest | str | None = None,
        progress: ProgressSink | ProgressReporter | None = None,
        *,
        source_id: str | None = None,
        path_prefix: str | None = None,
        limit: int | None = None,
        force: bool = False,
        workers: int = 1,
        track_timeout: float = 1800.0,
    ) -> AnalysisRunResult:
        """Analyze through the typed core request, retaining refresh compatibility."""
        effective = (
            request
            if isinstance(request, AnalyzeRequest)
            else AnalyzeRequest(
                source_id=request if isinstance(request, str) else source_id,
                path_prefix=path_prefix,
                limit=limit,
                force=force,
                workers=workers,
                track_timeout=track_timeout,
            )
        )
        return self._analyze_request(effective, progress=progress)

    def _scan_for_refresh(self, *, enabled_only: bool) -> list[ScanResult]:
        """Keep inherited refresh compatible with the typed scan contract."""
        return _legacy_scan_results(self.scan(ScanRequest(enabled_only=enabled_only)))

    @overload
    def export(
        self,
        facet: ExportRequest,
        *,
        type: str | None = None,
        format: str | None = None,
        fields: str | None = None,
    ) -> ExportResult: ...

    @overload
    def export(
        self,
        facet: str | None = None,
        *,
        type: str | None = None,
        format: str | None = None,
        fields: str | None = None,
    ) -> list[str]: ...

    def export(
        self,
        facet: str | ExportRequest | None = None,
        *,
        type: str | None = None,
        format: str | None = None,
        fields: str | None = None,
    ) -> ExportResult | list[str]:
        """Publish through the typed core export contract."""
        if isinstance(facet, ExportRequest):
            return ExportUseCase(self.database, self.config).execute(facet)
        return super().export(facet, type=type, format=format, fields=fields)

    def snapshot(self, request: Path | SnapshotRequest, archive: bool = False) -> SnapshotResult:
        """Publish through the typed core snapshot contract."""
        effective = (
            request if isinstance(request, SnapshotRequest) else SnapshotRequest(request, archive)
        )
        return SnapshotUseCase(self.database).execute(effective)


def _legacy_source(request: str | None, source_id: str | None) -> str | None:
    """Normalize the historical positional and keyword source arguments."""
    if request is not None and source_id is not None and request != source_id:
        raise ValueError("conflicting duplicate source identifiers")
    return request if request is not None else source_id


def _legacy_scan_results(result: ScanRunResult) -> list[ScanResult]:
    """Adapt one typed result for the historical application contract."""
    return [
        ScanResult(item.source_id, item.succeeded, item.run_id, item.error)
        for item in result.sources
    ]


def _worst_status(*statuses: str) -> str:
    order = {"succeeded": 0, "partial": 1, "failed": 2}
    return max(statuses, key=lambda status: order.get(status, 2))


def _has_chromaprint_muxer() -> bool:
    """Compatibility hook for tests and legacy callers."""
    return has_chromaprint_muxer()
