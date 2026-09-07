"""Workspace configuration loading and validation."""

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, field
from importlib.resources import as_file, files
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
        resource = files("dj_digger").joinpath("analysis.toml")
        if not resource.is_file():
            raise FileNotFoundError("required packaged resource missing: dj_digger/analysis.toml")
        with as_file(resource) as path:
            return cls.load(path)

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
class ComparisonThresholds:
    """Thresholds used for descriptive duplicate comparisons."""

    active_loudness_db: float | None = None
    true_peak_db: float | None = None
    plr_db: float | None = None
    integrated_lufs_db: float | None = None
    lra_lu: float | None = None
    gain_deficit_db: float | None = None


VARIANT_DEFAULTS = ComparisonThresholds(
    active_loudness_db=1.5,
    true_peak_db=1.0,
    plr_db=2.0,
    integrated_lufs_db=1.5,
    lra_lu=1.5,
)
REVIEW_DEFAULTS = ComparisonThresholds(
    active_loudness_db=1.5,
    true_peak_db=1.0,
    plr_db=2.0,
    gain_deficit_db=1.5,
)


@dataclass(frozen=True)
class MasteringConfig:
    """Optional targets and comparison thresholds for mastering analysis."""

    dj_target_lufs: float = -9.0
    dj_target_true_peak_dbtp: float = -1.0
    variant_thresholds: ComparisonThresholds = VARIANT_DEFAULTS
    review_thresholds: ComparisonThresholds = REVIEW_DEFAULTS


@dataclass(frozen=True)
class CurationConfig:
    """Bounded OpenAI-compatible curation runtime configuration."""

    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-5-mini"
    api_key_env: str = "OPENAI_API_KEY"
    request_timeout_seconds: float = 30.0
    total_timeout_seconds: float = 120.0
    max_turns: int = 8
    max_output_tokens: int = 2_000
    max_output_tracks: int = 20


@dataclass(frozen=True)
class WorkspaceConfig:
    """Immutable configuration for a DJ Digger workspace."""

    database: Path
    exports: Path
    sources: tuple[LibrarySourceConfig, ...]
    dsp: DspConfig = field(default_factory=DspConfig.canonical)
    dsp_path: Path | None = None
    mastering: MasteringConfig = field(default_factory=MasteringConfig)
    curation: CurationConfig = field(default_factory=CurationConfig)

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

        if "export" in raw_config:
            raise ValueError("[export] is no longer supported; remove this legacy table")

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
        mastering = _mastering_config(raw_config.get("mastering"))
        curation = _curation_config(raw_config.get("curation"))
        return cls(
            database,
            exports,
            tuple(sources),
            dsp,
            configured_dsp,
            mastering,
            curation,
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


def _optional_number(value: object, name: str) -> float | None:
    if value is None:
        return None
    return _number(value, name)


def _thresholds(value: object, name: str, defaults: ComparisonThresholds) -> ComparisonThresholds:
    table = {} if value is None else _mapping(value, name)
    fields = (
        "active_loudness_db",
        "true_peak_db",
        "plr_db",
        "integrated_lufs_db",
        "lra_lu",
        "gain_deficit_db",
    )
    parsed: dict[str, float | None] = {}
    for field_name in fields:
        raw = table.get(field_name, getattr(defaults, field_name))
        parsed_value = _optional_number(raw, f"{name}.{field_name}")
        parsed[field_name] = parsed_value
        if parsed_value is not None and parsed_value < 0:
            raise ValueError(f"{name}.{field_name} must not be negative")
    return ComparisonThresholds(**parsed)


def _mastering_config(value: object) -> MasteringConfig:
    if value is None:
        return MasteringConfig()
    table = _mapping(value, "mastering")
    target_lufs = _number(table.get("dj_target_lufs", -9.0), "mastering.dj_target_lufs")
    target_peak = _number(
        table.get("dj_target_true_peak_dbtp", -1.0),
        "mastering.dj_target_true_peak_dbtp",
    )
    return MasteringConfig(
        dj_target_lufs=target_lufs,
        dj_target_true_peak_dbtp=target_peak,
        variant_thresholds=_thresholds(
            table.get("variant_thresholds"), "mastering.variant_thresholds", VARIANT_DEFAULTS
        ),
        review_thresholds=_thresholds(
            table.get("review_thresholds"), "mastering.review_thresholds", REVIEW_DEFAULTS
        ),
    )


def _curation_config(value: object) -> CurationConfig:
    if value is None:
        return CurationConfig()
    table = _mapping(value, "curation")
    forbidden = {name for name in table if name.lower() in {"api_key", "key", "token", "secret"}}
    if forbidden:
        raise ValueError("curation secrets must be supplied only through an environment variable")
    defaults = CurationConfig()
    base_url = _non_empty_string(table.get("base_url", defaults.base_url), "curation.base_url")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("curation.base_url must be an HTTP(S) URL")
    model = _non_empty_string(table.get("model", defaults.model), "curation.model")
    api_key_env = _non_empty_string(
        table.get("api_key_env", defaults.api_key_env), "curation.api_key_env"
    )
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env) is None:
        raise ValueError("curation.api_key_env must be a valid environment variable name")
    request_timeout = _number(
        table.get("request_timeout_seconds", defaults.request_timeout_seconds),
        "curation.request_timeout_seconds",
    )
    total_timeout = _number(
        table.get("total_timeout_seconds", defaults.total_timeout_seconds),
        "curation.total_timeout_seconds",
    )
    max_turns = _integer(table.get("max_turns", defaults.max_turns), "curation.max_turns")
    max_tokens = _integer(
        table.get("max_output_tokens", defaults.max_output_tokens), "curation.max_output_tokens"
    )
    max_tracks = _integer(
        table.get("max_output_tracks", defaults.max_output_tracks), "curation.max_output_tracks"
    )
    if request_timeout <= 0 or total_timeout <= 0 or total_timeout < request_timeout:
        raise ValueError("curation timeouts must be positive and total must cover each request")
    if not 1 <= max_turns <= 32 or not 1 <= max_tokens <= 100_000 or not 1 <= max_tracks <= 20:
        raise ValueError("curation turn and output limits are outside supported bounds")
    return CurationConfig(
        base_url=base_url.rstrip("/"),
        model=model,
        api_key_env=api_key_env,
        request_timeout_seconds=request_timeout,
        total_timeout_seconds=total_timeout,
        max_turns=max_turns,
        max_output_tokens=max_tokens,
        max_output_tracks=max_tracks,
    )


def _non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
