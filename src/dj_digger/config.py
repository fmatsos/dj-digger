"""Workspace configuration loading and validation."""

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from math import isfinite
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
class DspConfig:
    """Versioned, canonical DSP runtime contract."""

    version: int
    sample_rate: int
    channels: int
    fft_window_size: int
    fft_hop_size: int
    bands: dict[str, tuple[float, float]]
    segmentation_min_seconds: float
    segmentation_max_seconds: float
    semantic_min_confidence: float

    @property
    def config_hash(self) -> str:
        payload = {
            "version": self.version,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "fft_window_size": self.fft_window_size,
            "fft_hop_size": self.fft_hop_size,
            "bands": {name: list(self.bands[name]) for name in sorted(self.bands)},
            "segmentation_min_seconds": self.segmentation_min_seconds,
            "segmentation_max_seconds": self.segmentation_max_seconds,
            "semantic_min_confidence": self.semantic_min_confidence,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def canonical(cls) -> "DspConfig":
        packaged = Path(__file__).with_name("analysis.toml")
        source_tree = Path(__file__).parents[2] / "config" / "analysis.toml"
        return cls.load(packaged if packaged.is_file() else source_tree)

    @classmethod
    def load(cls, path: Path) -> "DspConfig":
        with path.open("rb") as file:
            raw = tomllib.load(file)
        try:
            meta = raw["meta"]
            audio = raw["audio"]
            fft = raw["fft"]
            bands = raw["bands"]
            segmentation = raw["segmentation"]
            semantics = raw["semantics"]
        except (KeyError, TypeError):
            raise ValueError(
                "DSP configuration requires meta, audio, fft, bands, segmentation and semantics"
            ) from None
        version = _integer(meta.get("version"), "meta.version")
        sample_rate = _integer(audio.get("sample_rate"), "audio.sample_rate")
        channels = _integer(audio.get("channels"), "audio.channels")
        fft_window_size = _integer(fft.get("window_size"), "fft.window_size")
        fft_hop_size = _integer(fft.get("hop_size"), "fft.hop_size")
        if sample_rate != 48_000 or channels != 1:
            raise ValueError("DSP audio must be mono at 48000 Hz")
        if fft_window_size <= 0 or fft_hop_size <= 0:
            raise ValueError("DSP FFT window and hop must be positive")
        parsed_bands: dict[str, tuple[float, float]] = {}
        for name in ("sub", "low", "low_mid", "kick", "bass", "onset", "spectral"):
            values = bands.get(name)
            if not isinstance(values, list) or len(values) != 2:
                raise ValueError(f"DSP bands.{name} must contain two frequency limits")
            lower = _number(values[0], f"bands.{name}[0]")
            upper = _number(values[1], f"bands.{name}[1]")
            if upper < lower:
                raise ValueError(f"DSP bands.{name} has inverted limits")
            parsed_bands[name] = (lower, upper)
        minimum = _number(segmentation.get("min_seconds"), "segmentation.min_seconds")
        maximum = _number(segmentation.get("max_seconds"), "segmentation.max_seconds")
        confidence = _number(semantics.get("min_confidence"), "semantics.min_confidence")
        if maximum <= minimum or not 0 <= confidence <= 1:
            raise ValueError("DSP segmentation bounds or semantic confidence are invalid")
        return cls(
            version,
            sample_rate,
            channels,
            fft_window_size,
            fft_hop_size,
            parsed_bands,
            minimum,
            maximum,
            confidence,
        )


@dataclass(frozen=True)
class WorkspaceConfig:
    """Immutable configuration for a DJ Digger workspace."""

    database: Path
    exports: Path
    export: ExportConfig
    sources: tuple[LibrarySourceConfig, ...]
    dsp: DspConfig = field(default_factory=DspConfig.canonical)
    dsp_path: Path | None = None

    @classmethod
    def load(cls, path: Path, *, dsp_path: Path | None = None) -> "WorkspaceConfig":
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

        configured_dsp = dsp_path
        if configured_dsp is None:
            raw_dsp = workspace.get("dsp_config", "")
            if raw_dsp:
                configured_dsp = _resolve_path(raw_dsp, config_directory, "workspace.dsp_config")
        # Keep loading the workspace possible so `doctor` can report malformed DSP
        # configuration as a structured diagnostic instead of aborting config parsing.
        dsp = DspConfig.canonical()
        return cls(
            database,
            exports,
            ExportConfig(legacy_compatibility),
            tuple(sources),
            dsp,
            configured_dsp,
        )


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


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
