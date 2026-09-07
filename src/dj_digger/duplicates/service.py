"""Compatibility re-exports for the canonical duplicate service."""

from dj_digger.core.duplicates.service import (
    TECHNICAL_PROBE_VERSION,
    DuplicateAnalysisResult,
    DuplicateGroupDescription,
    DuplicateMemberDescription,
    DuplicateService,
)

__all__ = [
    "TECHNICAL_PROBE_VERSION",
    "DuplicateAnalysisResult",
    "DuplicateGroupDescription",
    "DuplicateMemberDescription",
    "DuplicateService",
]
