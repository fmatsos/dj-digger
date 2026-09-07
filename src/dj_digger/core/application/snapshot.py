"""Typed catalog snapshot use case."""

from dataclasses import dataclass
from pathlib import Path

from dj_digger.core.catalog.database import Database
from dj_digger.core.exports.snapshot import SnapshotExporter, SnapshotResult


@dataclass(frozen=True)
class SnapshotRequest:
    """Destination and archive options for one catalog snapshot."""

    output: Path
    archive: bool = False


class SnapshotUseCase:
    """Publish a validated snapshot through the canonical exporter."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def execute(self, request: SnapshotRequest) -> SnapshotResult:
        return SnapshotExporter(self._database).create(request.output, request.archive)


__all__ = ["SnapshotRequest", "SnapshotResult", "SnapshotUseCase"]
