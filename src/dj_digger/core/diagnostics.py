"""The machine-readable contract of one CLI command run.

This is a presentation contract, deliberately distinct from a catalog run
state: ``partial`` exists here (some work succeeded, some failed) and has no
equivalent in the catalog, while ``running`` exists in the catalog and never
appears in a completed diagnostic.

Payload shapes are ``TypedDict``s rather than ``dict[str, Any]`` so a presenter
that drops ``status``, misspells ``event`` or renames a published field fails
the type check instead of silently changing the JSON other tools consume.
"""

from enum import StrEnum
from typing import Any, NotRequired, TypedDict


class DiagnosticStatus(StrEnum):
    """Terminal status of one CLI command, mapped to its process exit code."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    BACKGROUND = "background"


class Diagnostic(TypedDict):
    """The envelope every command payload shares."""

    event: str
    status: str


class FailureDiagnostic(Diagnostic):
    """A command that could not complete."""

    error: str
    error_class: NotRequired[str]
    code: NotRequired[str]


class BackgroundDiagnostic(Diagnostic):
    """A command that was detached instead of run in the foreground."""

    job_id: str
    pid: int
    log: str


class ScanDiagnostic(Diagnostic):
    """Per-source outcome of one scan run."""

    scans: list[dict[str, Any]]


class MetadataDiagnostic(Diagnostic):
    extracted: int
    failed: int
    skipped: int


class AnalyzeDiagnostic(Diagnostic):
    run_id: int | None
    eligible: int
    analyzed: int
    reused: int
    failed: int


class ExportDiagnostic(Diagnostic):
    exports: list[str]


class SnapshotDiagnostic(Diagnostic):
    directory: str
    archive: str | None


class JobsDiagnostic(Diagnostic):
    jobs: list[dict[str, Any]]


def open_diagnostic(event: str, status: str, **fields: Any) -> dict[str, Any]:
    """Build a payload whose extra keys are taken from a result object.

    Some payloads splat a result's fields and cannot be a closed ``TypedDict``.
    Routing them through here still makes the envelope a compile-time
    requirement: ``event`` and ``status`` are positional and cannot be omitted.
    """
    return {"event": event, "status": status, **fields}


__all__ = [
    "AnalyzeDiagnostic",
    "BackgroundDiagnostic",
    "Diagnostic",
    "DiagnosticStatus",
    "ExportDiagnostic",
    "FailureDiagnostic",
    "JobsDiagnostic",
    "MetadataDiagnostic",
    "open_diagnostic",
    "ScanDiagnostic",
    "SnapshotDiagnostic",
]
