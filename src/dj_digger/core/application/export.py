"""Typed catalog export use case and publication result contracts."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dj_digger.core.analysis.exporters import AnalysisExporter
from dj_digger.core.catalog.database import Database
from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.errors import DependencyError, InvalidInputError
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
class ExportMaintenanceWarning:
    """Non-fatal maintenance warning after a committed publication."""

    code: str
    message: str


@dataclass(frozen=True)
class ExportResult:
    """Typed facets published by one immutable export generation.

    Consumers reading more than one facet must resolve and retain
    ``generation_path`` for the whole read, and must finish that grouped read
    before starting or allowing the next publication.  The path is kept
    through one immediately concurrent publication as the previous generation;
    it is not a durable interprocess lease and may be removed after a second
    later publication.  The public facet paths remain stable compatibility
    paths, but resolving them independently around a publication switch cannot
    provide a cross-file snapshot.
    """

    facets: tuple[PublishedFacet, ...]
    generation_path: Path
    maintenance_warning: ExportMaintenanceWarning | None = None

    @property
    def paths(self) -> tuple[Path, ...]:
        """Return published paths in deterministic publication order."""
        return tuple(facet.path for facet in self.facets)


class ExportUseCase:
    """Validate and atomically publish one consistent catalog export.

    Publication uses a POSIX directory symlink switch.  The destination is
    never silently replaced by a non-atomic fallback when symlinks are not
    available on the filesystem.
    """

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
            published = self._publish_group(destination, staged_facets, staged_destination)
            return ExportResult(
                published.facets,
                published.generation_path,
                published.maintenance_warning,
            )
        except ValueError as error:
            message = str(error)
            if message.startswith("--fields") or message.startswith("unknown field"):
                raise InvalidInputError(message) from error
            raise
        finally:
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
    ) -> _PublishedGroup:
        destination.parent.mkdir(parents=True, exist_ok=True)
        relative_facets = [
            (facet, facet.path.relative_to(staged_destination)) for facet in staged_facets
        ]
        storage = destination.parent / ".dj-digger-publications"
        _validate_storage_path(storage)
        _ensure_symlink_support(destination.parent)
        generation: Path | None = None
        next_link: Path | None = None
        previous_directory: Path | None = None
        previous_generation: Path | None = None
        switched = False
        try:
            _validate_storage_path(storage)
            storage.mkdir(exist_ok=True)
            _validate_storage_path(storage)
            storage_root = storage.resolve()
            if destination.is_symlink() and destination.exists():
                current = destination.resolve(strict=True)
                if current.is_dir() and current.is_relative_to(storage_root):
                    previous_generation = current
            generation = Path(tempfile.mkdtemp(prefix="generation-", dir=storage))
            generation.rmdir()
            os.replace(staged_destination, generation)
            if destination.exists() and not destination.is_symlink():
                if not destination.is_dir():
                    raise NotADirectoryError(
                        f"export destination is not a directory: {destination}"
                    )
                previous_directory = Path(tempfile.mkdtemp(prefix="generation-", dir=storage))
                previous_directory.rmdir()
                os.replace(destination, previous_directory)
                previous_generation = previous_directory
            next_link = _temporary_link(destination)
            os.symlink(
                Path(storage.name) / generation.name,
                next_link,
                target_is_directory=True,
            )
            os.replace(next_link, destination)
            switched = True
            generation_path = generation.resolve(strict=True)
        except BaseException:
            if switched:
                raise
            if next_link is not None:
                next_link.unlink(missing_ok=True)
            if previous_directory is not None and previous_directory.exists():
                os.replace(previous_directory, destination)
            raise
        finally:
            if next_link is not None and not switched:
                next_link.unlink(missing_ok=True)
            if generation is not None and not switched:
                shutil.rmtree(generation, ignore_errors=True)
        assert generation is not None
        maintenance_warning: ExportMaintenanceWarning | None = None
        try:
            _cleanup_generations(storage, {generation_path, previous_generation})
        except Exception:
            maintenance_warning = ExportMaintenanceWarning(
                code="publication_cleanup_deferred",
                message="generation cleanup was deferred after the publication succeeded",
            )
        return _PublishedGroup(
            tuple(
                PublishedFacet(destination / relative, facet.row_count)
                for facet, relative in relative_facets
            ),
            generation_path,
            maintenance_warning,
        )

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


__all__ = [
    "ExportMaintenanceWarning",
    "ExportRequest",
    "ExportResult",
    "ExportUseCase",
]


@dataclass(frozen=True)
class _PublishedGroup:
    facets: tuple[PublishedFacet, ...]
    generation_path: Path
    maintenance_warning: ExportMaintenanceWarning | None


def _validate_storage_path(storage: Path) -> None:
    """Reject symlinked publication storage before resolving or cleaning it."""
    if storage.is_symlink():
        raise DependencyError(
            f"publication storage must be a real directory, not a symlink: {storage.name}"
        )
    if storage.exists() and not storage.is_dir():
        raise DependencyError(f"publication storage is not a directory: {storage.name}")


def _ensure_symlink_support(parent: Path) -> None:
    """Fail before moving an existing export if directory symlinks are unavailable."""
    target: Path | None = None
    link: Path | None = None
    try:
        target = Path(tempfile.mkdtemp(prefix=".dj-digger-symlink-target-", dir=parent))
        descriptor, name = tempfile.mkstemp(prefix=".dj-digger-symlink-probe-", dir=parent)
        os.close(descriptor)
        link = Path(name)
        link.unlink()
        os.symlink(target.name, link, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        raise DependencyError(
            "atomic export publication requires POSIX directory symlink support "
            "on the export filesystem"
        ) from error
    finally:
        if link is not None:
            link.unlink(missing_ok=True)
        if target is not None:
            shutil.rmtree(target, ignore_errors=True)


def _cleanup_generations(storage: Path, keep: set[Path | None]) -> None:
    """Keep only the active generation and one previous generation."""
    retained = {path.resolve() for path in keep if path is not None}
    for child in storage.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        if not (child.name.startswith("generation-") or child.name.startswith("previous-")):
            continue
        if child.resolve() not in retained:
            shutil.rmtree(child)


def _temporary_link(destination: Path) -> Path:
    """Reserve a same-directory path for an atomic symlink replacement."""
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}-link-", dir=destination.parent)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path
