"""The status vocabulary of the CLI's machine-readable diagnostics.

This is a presentation contract, deliberately distinct from a catalog run
state: ``partial`` exists here (some work succeeded, some failed) and has no
equivalent in the catalog, while ``running`` exists in the catalog and never
appears in a completed diagnostic.
"""

from enum import StrEnum


class DiagnosticStatus(StrEnum):
    """Terminal status of one CLI command, mapped to its process exit code."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    BACKGROUND = "background"


__all__ = ["DiagnosticStatus"]
