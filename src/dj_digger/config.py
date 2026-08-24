"""Workspace configuration loading and validation."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LibrarySourceConfig:
    """One configured source library."""

    id: str
    path: Path
    set_eligible: bool
    analyze: bool
    enabled: bool = True


@dataclass(frozen=True)
class ExportConfig:
    """Export compatibility options."""

    legacy_compatibility: bool = True


@dataclass(frozen=True)
class WorkspaceConfig:
    """Immutable configuration for a DJ Digger workspace."""

    database: Path
    exports: Path
    export: ExportConfig
    sources: tuple[LibrarySourceConfig, ...]

    @classmethod
    def load(cls, path: Path) -> "WorkspaceConfig":
        """Load workspace configuration from a TOML file."""
        config_path = path.resolve()
        with config_path.open("rb") as file:
            raw_config = tomllib.load(file)

        workspace = _mapping(raw_config.get("workspace"), "workspace")
        config_directory = config_path.parent
        database = _resolve_path(workspace.get("database"), config_directory, "workspace.database")
        exports = _resolve_path(workspace.get("exports"), config_directory, "workspace.exports")

        export = _mapping(raw_config.get("export", {}), "export")
        legacy_compatibility = _boolean(
            export.get("legacy_compatibility", True), "export.legacy_compatibility"
        )

        library = _mapping(raw_config.get("library"), "library")
        raw_sources = library.get("sources")
        if not isinstance(raw_sources, list):
            raise ValueError("library.sources must be an array")

        source_ids: set[str] = set()
        sources: list[LibrarySourceConfig] = []
        for index, raw_source in enumerate(raw_sources):
            source_table = _mapping(raw_source, f"library.sources[{index}]")
            source_id = source_table.get("id")
            if not isinstance(source_id, str) or not source_id.strip():
                raise ValueError("source id must not be blank")
            if source_id in source_ids:
                raise ValueError(f"duplicate source id: {source_id}")
            source_ids.add(source_id)
            sources.append(
                LibrarySourceConfig(
                    id=source_id,
                    path=_resolve_path(source_table.get("path"), config_directory, "source.path"),
                    set_eligible=_boolean(source_table.get("set_eligible"), "source.set_eligible"),
                    analyze=_boolean(source_table.get("analyze"), "source.analyze"),
                    enabled=_boolean(source_table.get("enabled", True), "source.enabled"),
                )
            )

        for source in sources:
            if _is_within(database, source.path) or _is_within(exports, source.path):
                raise ValueError("workspace database and exports must not be inside source roots")

        return cls(database, exports, ExportConfig(legacy_compatibility), tuple(sources))


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a table")
    return value


def _resolve_path(value: object, base_directory: Path, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty path")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base_directory / candidate
    return candidate.resolve()


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
