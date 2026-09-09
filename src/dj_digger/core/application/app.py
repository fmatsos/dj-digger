"""Application-level orchestration for the DJ Digger command line."""

import importlib.util
import shutil
from pathlib import Path
from types import TracebackType
from typing import Self

from dj_digger.core.analysis.config import (
    CURRENT_ANALYZER_VERSION,
    DEFAULT_TRACK_TIMEOUT_SECONDS,
    DEFAULT_WORKERS,
    AnalysisIdentity,
)
from dj_digger.core.analysis.pipeline import (
    AnalysisExtractor,
    AnalysisRunResult,
    TimedAnalysisExtractor,
)
from dj_digger.core.analysis.worker_client import IsolatedAnalysisExtractor
from dj_digger.core.application.analysis_progress import ProgressEventReporter, ProgressReporter
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
from dj_digger.core.application.refresh import RefreshRequest, RefreshResult, RefreshUseCase
from dj_digger.core.application.scan import (
    ScanRequest,
    ScanRunResult,
    ScanUseCase,
)
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
)
from dj_digger.core.errors import (
    InvalidInputError,
    ResourceNotFoundError,
    StateConflictError,
)
from dj_digger.core.exports.curation import (
    CurationExportContent,
    CurationExportResult,
    export_curation,
)


class CoreApplication:
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

    def scan(self, request: ScanRequest | None = None) -> ScanRunResult:
        """Scan configured sources through the typed core request contract."""
        return self._scan_result(request or ScanRequest())

    def _scan_result(self, request: ScanRequest) -> ScanRunResult:
        """Execute one canonical scan orchestration for all application facades."""
        return ScanUseCase(self.database, self.config).execute(request)

    def metadata(
        self,
        request: MetadataRequest | None = None,
    ) -> MetadataRunResult:
        return self._metadata_result(request or MetadataRequest())

    def _metadata_result(self, request: MetadataRequest) -> MetadataRunResult:
        """Execute one canonical metadata orchestration for all facades."""
        return MetadataUseCase(self.database).execute(request)

    def analyze(
        self,
        request: AnalyzeRequest | None = None,
        progress: ProgressSink | ProgressReporter | None = None,
    ) -> AnalysisRunResult:
        """Analyze through the typed core request contract."""
        return self._analyze_request(request or AnalyzeRequest(), progress=progress)

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
        request: DuplicateAnalyzeRequest,
        *,
        progress: ProgressReporter | ProgressSink | None = None,
    ) -> DuplicateAnalysisResult:
        """Run duplicate analysis through the typed core request contract."""
        return self._duplicate_analyze_request(request, progress=progress)

    def _duplicate_analyze_request(
        self,
        request: DuplicateAnalyzeRequest,
        *,
        progress: ProgressReporter | ProgressSink | None = None,
    ) -> DuplicateAnalysisResult:
        self._require_duplicate_source(request.source_id)
        reporter = ProgressEventReporter(progress) if callable(progress) else progress
        return DuplicateAnalyzeUseCase(
            self.database,
            {source.id: source.path for source in self.config.sources},
            mastering_config=self.config.mastering,
        ).execute(request, progress=reporter)

    def duplicates_list(
        self,
        request: DuplicateListRequest,
    ) -> list[DuplicateGroupDescription]:
        """List duplicate groups through the typed core request contract."""
        return self._duplicate_list_request(request)

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
        request: DuplicateMarkBestRequest,
    ) -> QualityMarkResult:
        """Mark the best-quality copy through the typed core request contract."""
        return self._duplicate_mark_best_request(request)

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
        self._selected_sources(source_id, enabled_only=True)

    async def create_curation(self, request: CurationRequest) -> CurationResult:
        """Run and persist one catalog-grounded draft asynchronously."""
        return await CurationUseCase(self.config).execute(request)

    def get_curation(self, creation_id: str) -> CurationCreation | None:
        """Return one durable curation."""
        return CurationRepository(self.database).get(creation_id)

    def list_curations(self, status: CurationStatus | None = None) -> tuple[CurationCreation, ...]:
        """List durable curations for CLI and future web consumers."""
        return CurationRepository(self.database).list(status)

    def validate_curation(self, creation_id: str) -> CurationCreation:
        """Explicitly transition a draft to validated."""
        curations = CurationRepository(self.database)
        creation = curations.get(creation_id)
        if creation is None:
            raise ResourceNotFoundError("unknown curation ID")
        if creation.status != "draft":
            raise StateConflictError("curation is already validated")
        return curations.validate(creation_id)

    def export_curation(
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

    def export(self, request: ExportRequest) -> ExportResult:
        """Publish one typed export request."""
        return ExportUseCase(self.database, self.config).execute(request)

    def snapshot(self, request: SnapshotRequest) -> SnapshotResult:
        """Publish one typed snapshot request."""
        return SnapshotUseCase(self.database).execute(request)

    def refresh(
        self,
        request: RefreshRequest | None = None,
        *,
        workers: int = DEFAULT_WORKERS,
        track_timeout: float = DEFAULT_TRACK_TIMEOUT_SECONDS,
        progress: ProgressReporter | ProgressSink | None = None,
    ) -> RefreshResult:
        """Run scan, metadata, analysis, and one atomic export publication."""
        effective = request or RefreshRequest(workers=workers, track_timeout=track_timeout)
        if request is not None and (
            workers != DEFAULT_WORKERS or track_timeout != DEFAULT_TRACK_TIMEOUT_SECONDS
        ):
            raise InvalidInputError("refresh request conflicts with worker options")
        return RefreshUseCase(
            self.database,
            self.config,
            self._analysis_identity,
            self._analysis_extractor,
            scan=self._refresh_scan_dependency,
            metadata=self._refresh_metadata_dependency,
            analyze=self._refresh_analyze_dependency,
            export=self._refresh_export_dependency,
        ).execute(effective, progress=progress)

    def _refresh_scan_dependency(self, request: ScanRequest) -> ScanRunResult:
        return self.scan(request)

    def _refresh_metadata_dependency(self, request: MetadataRequest) -> MetadataRunResult:
        return self.metadata(request)

    def _refresh_analyze_dependency(
        self, request: AnalyzeRequest, progress: ProgressReporter | ProgressSink
    ) -> AnalysisRunResult:
        return self.analyze(request, progress)

    def _refresh_export_dependency(self, request: ExportRequest) -> ExportResult:
        return self.export(request)

    def status(self) -> StatusResult:
        return StatusUseCase(self.database, self.config).execute()

    def optimize_database(self) -> DatabaseOptimizeResult:
        """Run SQLite's bounded planner-statistics maintenance."""
        return OptimizeDatabaseUseCase(self.database).execute()

    def quick_check_database(self) -> DatabaseQuickCheckResult:
        """Run the lightweight SQLite consistency check explicitly."""
        return QuickCheckDatabaseUseCase(self.database).execute()

    def integrity_check_database(self) -> DatabaseIntegrityCheckResult:
        """Run SQLite's full integrity check explicitly."""
        return IntegrityCheckDatabaseUseCase(self.database).execute()

    def rebuild_current_analysis(self) -> DatabaseRebuildResult:
        """Rebuild the derived latest-success projection, then update planner statistics."""
        return RebuildCurrentAnalysisUseCase(self.database).execute()

    def doctor(self) -> DoctorResult:
        return DoctorUseCase(
            self.database,
            self.config,
            chromaprint_check=_has_chromaprint_muxer,
            which=shutil.which,
            find_spec=importlib.util.find_spec,
        ).execute()

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
            raise ResourceNotFoundError(f"unknown or disabled source: {source_id}")
        return selected


def _has_chromaprint_muxer() -> bool:
    """Return whether the duplicate-analysis runtime dependency is available."""
    return has_chromaprint_muxer()
