"""Versioned identity for reusable audio analysis results."""

from dataclasses import dataclass

CURRENT_ANALYZER_VERSION = "dj-digger-analysis/3"

#: Wall-clock budget for one track, shared by the CLI, the pipeline and duplicates.
DEFAULT_TRACK_TIMEOUT_SECONDS = 1800.0
DEFAULT_WORKERS = 1


@dataclass(frozen=True)
class AnalysisIdentity:
    """The analysis facts that must match before a result can be reused."""

    schema_version: int
    analyzer_version: str
    config_hash: str
