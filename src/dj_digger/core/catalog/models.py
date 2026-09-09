"""Catalog value objects and the state vocabularies they carry.

Members keep the exact text stored in SQLite: ``StrEnum`` values bind as TEXT
parameters and compare equal to the literals already used in SQL and in
export payloads, so naming a state never changes what is persisted.

SQL bodies deliberately keep their literals. The catalog's partial indexes are
defined with ``WHERE presence_status = 'present'`` and
``WHERE analysis_status = 'succeeded'``; SQLite only matches a partial index
when the query repeats that literal, so parameterising those predicates would
silently drop the index.
"""

from dataclasses import dataclass
from enum import StrEnum


class PresenceStatus(StrEnum):
    """Whether a catalogued track was observed on disk by the last scan."""

    PRESENT = "present"
    MISSING = "missing"


class RunStatus(StrEnum):
    """Lifecycle of one scan or analysis run."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AnalysisAttemptStatus(StrEnum):
    """Outcome of one immutable analysis attempt for a track."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class Track:
    """A source-scoped track stored in the catalog."""

    id: int
    source_id: str
    relative_path: str
    filename: str
    extension: str
    size_bytes: int
    mtime_ns: int
    presence_status: PresenceStatus


__all__ = ["AnalysisAttemptStatus", "PresenceStatus", "RunStatus", "Track"]
