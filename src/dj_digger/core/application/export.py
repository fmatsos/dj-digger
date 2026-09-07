"""Typed catalog export use case and publication result contracts."""

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dj_digger.core.analysis.exporters import AnalysisExporter
from dj_digger.core.application.errors import InvalidInputError
from dj_digger.core.catalog.database import Database
from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.exports.audit import AuditExporter
from dj_digger.core.exports.tracks import PublishedFacet, TracksExporter


@dataclass(frozen=True)
class ExportRequest:
    """Selection and output options for one catalog publication."""

    facet: str | None = None
    type: str | None = None
    format: str | None = None
    fields: str | None = None


@dataclass(frozen=True)
class ExportResult:
    """Typed facets published by one export run."""

    facets: tuple[PublishedFacet, ...]

    @property
    def paths(self) -> tuple[Path, ...]:
        """Return published paths in deterministic publication order."""
        return tuple(facet.path for facet in self.facets)


class ExportUseCase:
    """Validate and atomically publish one consistent catalog export."""

    _FACETS = {"tracks", "artifacts", "analysis"}
    _TYPES = _FACETS | {"all", "sections", "run"}
    _ANALYSIS_TYPES = {"analysis", "sections", "run"}

    def __init__(self, database: Database, config: WorkspaceConfig) -> None:
        self._database = database
        self._config = config

    def execute(self, request: ExportRequest | None = None) -> ExportResult:
        request = request or ExportRequest()
        selected = self._validate(request)
        destination = self._config.exports
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
        staged_destination = staging / "publication"
        try:
            with self._database.read_transaction():
                staged_facets = self._publish_to_staging(staged_destination, request, selected)
            facets = self._publish_group(destination, staged_facets, staged_destination)
            return ExportResult(tuple(facets))
        except ValueError as error:
            shutil.rmtree(staging, ignore_errors=True)
            message = str(error)
            if message.startswith("--fields") or message.startswith("unknown field"):
                raise InvalidInputError(message) from error
            raise
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        else:
            shutil.rmtree(staging, ignore_errors=True)

    def _publish_to_staging(
        self, destination: Path, request: ExportRequest, selected: str | None
    ) -> list[PublishedFacet]:
        facets: list[PublishedFacet] = []
        analysis_type = request.type if request.type in self._ANALYSIS_TYPES else None
        if selected in {None, "analysis"} or analysis_type is not None:
            facets.extend(
                AnalysisExporter(self._database).export(
                    destination,
                    format=request.format,
                    fields=request.fields,
                    leaf_type=analysis_type,
                )
            )
        if selected in {None, "tracks"}:
            facets.append(
                TracksExporter(self._database).export(
                    destination / "tracks.tsv",
                    format=request.format,
                    fields=request.fields,
                )
            )
        if selected in {None, "artifacts"}:
            facets.extend(
                AuditExporter(self._database).export(
                    destination,
                    format=request.format,
                    fields=request.fields,
                )
            )
        return facets

    @staticmethod
    def _publish_group(
        destination: Path, staged_facets: list[PublishedFacet], staged_destination: Path
    ) -> list[PublishedFacet]:
        destination.mkdir(parents=True, exist_ok=True)
        targets = [
            (facet.path, destination / facet.path.relative_to(staged_destination))
            for facet in staged_facets
        ]
        backups: list[tuple[Path, Path]] = []
        replaced: list[Path] = []
        try:
            for index, (_, target) in enumerate(targets):
                if target.exists():
                    backup = staged_destination.parent / f".backup-{index}"
                    os.replace(target, backup)
                    backups.append((target, backup))
            for source, target in targets:
                os.replace(source, target)
                replaced.append(target)
        except BaseException:
            for target in replaced:
                target.unlink(missing_ok=True)
            for target, backup in backups:
                if backup.exists():
                    os.replace(backup, target)
            raise
        return [
            PublishedFacet(target, facet.row_count)
            for facet, (_, target) in zip(staged_facets, targets, strict=True)
        ]

    @classmethod
    def _validate(cls, request: ExportRequest) -> str | None:
        if request.facet not in {None, "all", *cls._FACETS}:
            raise InvalidInputError(f"unknown export facet: {request.facet}")
        if request.type is not None and request.type not in cls._TYPES:
            raise InvalidInputError(f"unknown export type: {request.type}")
        if request.fields is not None and request.type in {None, "all"}:
            raise InvalidInputError("--fields requires a leaf --type")
        if (
            request.type is not None
            and request.type != "all"
            and request.facet
            not in {
                None,
                request.type,
                "analysis" if request.type in cls._ANALYSIS_TYPES else request.type,
            }
        ):
            raise InvalidInputError("--type and --facet select different exports")
        if request.format is not None and request.format not in {"json", "csv", "tsv"}:
            raise InvalidInputError(f"unknown export format: {request.format}")
        selected = request.type or request.facet
        return None if selected in {None, "all"} else selected


__all__ = ["ExportRequest", "ExportResult", "ExportUseCase"]
