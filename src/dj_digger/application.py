"""Compatibility imports for the migrated application boundary."""

import importlib.util
import shutil

from dj_digger.analysis.worker_client import IsolatedAnalysisExtractor
from dj_digger.core.application.app import (
    CoreApplication,
    ScanResult,
    WorkspaceApplication,
    _has_chromaprint_muxer,
)
from dj_digger.core.catalog.database import Database

__all__ = [
    "CoreApplication",
    "Database",
    "IsolatedAnalysisExtractor",
    "ScanResult",
    "WorkspaceApplication",
    "_has_chromaprint_muxer",
    "importlib",
    "shutil",
]
