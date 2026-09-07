"""Compatibility imports for the migrated application boundary."""

from dj_digger.core.analysis.worker_client import IsolatedAnalysisExtractor
from dj_digger.core.application.app import (
    CoreApplication,
    ScanResult,
    WorkspaceApplication,
    _has_chromaprint_muxer,
)
from dj_digger.core.application.refresh import RefreshRequest, RefreshResult, RefreshUseCase
from dj_digger.core.catalog.database import Database

__all__ = [
    "CoreApplication",
    "Database",
    "IsolatedAnalysisExtractor",
    "ScanResult",
    "RefreshRequest",
    "RefreshResult",
    "RefreshUseCase",
    "WorkspaceApplication",
    "_has_chromaprint_muxer",
]
