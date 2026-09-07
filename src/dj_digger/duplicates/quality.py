"""Compatibility re-exports for canonical duplicate quality selection."""

from dj_digger.core.duplicates.quality import (
    RANKING_VERSION,
    QualityMarkResult,
    QualitySelector,
    TechnicalFacts,
)

__all__ = ["RANKING_VERSION", "QualityMarkResult", "QualitySelector", "TechnicalFacts"]
