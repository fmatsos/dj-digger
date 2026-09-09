"""Typed metadata refresh use case."""

from dataclasses import dataclass

from dj_digger.core.catalog.database import Database
from dj_digger.core.errors import InvalidInputError
from dj_digger.core.metadata.exiftool import ExifToolExtractor, MetadataRunResult, MetadataService


@dataclass(frozen=True)
class MetadataRequest:
    """Scope for one embedded metadata refresh."""

    source_id: str | None = None
    path_prefix: str | None = None
    force: bool = False


class MetadataUseCase:
    """Validate and execute one metadata refresh against the core catalog."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def execute(self, request: MetadataRequest) -> MetadataRunResult:
        if request.path_prefix is not None and not request.path_prefix.strip():
            raise InvalidInputError("path prefix must not be blank")
        return MetadataService(self._database, ExifToolExtractor()).refresh(
            request.source_id,
            force=request.force,
            path_prefix=request.path_prefix,
        )


__all__ = ["MetadataRequest", "MetadataRunResult", "MetadataUseCase"]
