"""Public application use cases and contracts."""

from typing import Any

from dj_digger.core.application.analysis_progress import (
    AnalysisProgressReporter,
    NullProgressReporter,
    ProgressEventReporter,
    ProgressReporter,
)
from dj_digger.core.application.curation import (
    CurationAuthenticationError,
    CurationClientError,
    CurationGroundingError,
    CurationMCPError,
    CurationRequest,
    CurationResponseError,
    CurationResult,
    CurationTimeoutError,
    CurationTransportError,
    CurationTurnLimitError,
    CurationUseCase,
)
from dj_digger.core.application.errors import (
    CoreError,
    DependencyError,
    DependencyTimeoutError,
    IntegrityError,
    InvalidInputError,
    ResourceNotFoundError,
    StateConflictError,
)
from dj_digger.core.application.export import (
    ExportMaintenanceWarning,
    ExportRequest,
    ExportResult,
    ExportUseCase,
)
from dj_digger.core.application.jobs import (
    JobRecord,
    JobRepository,
    JobStateError,
    JobStatus,
    JobsUseCase,
)
from dj_digger.core.application.metadata import MetadataRequest, MetadataRunResult, MetadataUseCase
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
)
from dj_digger.core.application.progress import ProgressEvent, ProgressSink
from dj_digger.core.application.scan import (
    ScanRequest,
    ScanRunResult,
    ScanSourceResult,
)

__all__ = [
    "CoreApplication",
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
    "CurationUseCase",
    "CopySetRequest",
    "CopySetUseCase",
    "SetCopyResult",
    "ExportRequest",
    "ExportResult",
    "ExportUseCase",
    "ExportMaintenanceWarning",
    "AnalyzeRequest",
    "AnalyzeUseCase",
    "DatabaseIntegrityCheckResult",
    "DatabaseOptimizeResult",
    "DatabaseQuickCheckResult",
    "DatabaseRebuildResult",
    "DuplicateAnalysisResult",
    "DuplicateAnalyzeRequest",
    "DuplicateAnalyzeUseCase",
    "DuplicateGroupDescription",
    "DuplicateListRequest",
    "DuplicateListUseCase",
    "DuplicateMarkBestRequest",
    "DuplicateMarkBestUseCase",
    "DoctorResult",
    "DoctorUseCase",
    "AnalysisProgressReporter",
    "CoreError",
    "DependencyError",
    "DependencyTimeoutError",
    "IntegrityError",
    "InvalidInputError",
    "IntegrityCheckDatabaseUseCase",
    "JobRecord",
    "JobRepository",
    "JobStateError",
    "JobStatus",
    "JobsUseCase",
    "MetadataRequest",
    "MetadataRunResult",
    "MetadataUseCase",
    "ProgressEvent",
    "ProgressEventReporter",
    "ProgressReporter",
    "ProgressSink",
    "RefreshRequest",
    "RefreshResult",
    "RefreshUseCase",
    "QualityMarkResult",
    "NullProgressReporter",
    "OptimizeDatabaseUseCase",
    "QuickCheckDatabaseUseCase",
    "RebuildCurrentAnalysisUseCase",
    "ResourceNotFoundError",
    "ScanRequest",
    "ScanRunResult",
    "ScanSourceResult",
    "StateConflictError",
    "StatusResult",
    "StatusUseCase",
    "SnapshotRequest",
    "SnapshotResult",
    "SnapshotUseCase",
    "worst_status",
]


def __getattr__(name: str) -> Any:
    """Load application facades lazily so analysis modules remain acyclic."""
    if name == "CoreApplication":
        from dj_digger.core.application.app import CoreApplication

        return CoreApplication
    if name in {"CopySetRequest", "CopySetUseCase", "SetCopyResult"}:
        from dj_digger.core.application.copy_set import (
            CopySetRequest,
            CopySetUseCase,
            SetCopyResult,
        )

        return {
            "CopySetRequest": CopySetRequest,
            "CopySetUseCase": CopySetUseCase,
            "SetCopyResult": SetCopyResult,
        }[name]
    if name in {"AnalyzeRequest", "AnalyzeUseCase"}:
        from dj_digger.core.application.analyze import AnalyzeRequest, AnalyzeUseCase

        return {"AnalyzeRequest": AnalyzeRequest, "AnalyzeUseCase": AnalyzeUseCase}[name]
    if name in {"RefreshRequest", "RefreshResult", "RefreshUseCase", "worst_status"}:
        from dj_digger.core.application.refresh import (
            RefreshRequest,
            RefreshResult,
            RefreshUseCase,
            worst_status,
        )

        return {
            "RefreshRequest": RefreshRequest,
            "RefreshResult": RefreshResult,
            "RefreshUseCase": RefreshUseCase,
            "worst_status": worst_status,
        }[name]
    duplicate_names = {
        "DuplicateAnalysisResult",
        "DuplicateAnalyzeRequest",
        "DuplicateAnalyzeUseCase",
        "DuplicateGroupDescription",
        "DuplicateListRequest",
        "DuplicateListUseCase",
        "DuplicateMarkBestRequest",
        "DuplicateMarkBestUseCase",
        "QualityMarkResult",
    }
    if name in duplicate_names:
        from dj_digger.core.application import duplicates

        return getattr(duplicates, name)
    if name in {"SnapshotRequest", "SnapshotResult", "SnapshotUseCase"}:
        from dj_digger.core.application.snapshot import (
            SnapshotRequest,
            SnapshotResult,
            SnapshotUseCase,
        )

        return {
            "SnapshotRequest": SnapshotRequest,
            "SnapshotResult": SnapshotResult,
            "SnapshotUseCase": SnapshotUseCase,
        }[name]
    raise AttributeError(name)
