"""Catalog value objects."""

from dataclasses import dataclass


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
    presence_status: str
