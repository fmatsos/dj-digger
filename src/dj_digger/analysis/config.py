"""Versioned identity for reusable audio analysis results."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisIdentity:
    """The analysis facts that must match before a result can be reused."""

    schema_version: int
    analyzer_version: str
    config_hash: str
