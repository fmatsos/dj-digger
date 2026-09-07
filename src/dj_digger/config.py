"""Compatibility imports for configuration contracts."""

from importlib.resources import files

from dj_digger.core.config import (
    REVIEW_DEFAULTS,
    VARIANT_DEFAULTS,
    ComparisonThresholds,
    CurationConfig,
    DspConfig,
    LibrarySourceConfig,
    MasteringConfig,
    WorkspaceConfig,
)

__all__ = [
    "ComparisonThresholds",
    "CurationConfig",
    "DspConfig",
    "LibrarySourceConfig",
    "MasteringConfig",
    "REVIEW_DEFAULTS",
    "VARIANT_DEFAULTS",
    "WorkspaceConfig",
    "files",
]
