"""Pure, configurable normalization of low-end and spectral audio facts."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Protocol

import numpy as np

FACT_NAMES = ("sub", "low", "low_mid", "kick", "bass", "onset", "spectral")


@dataclass(frozen=True)
class SpectrumFacts:
    sub: float
    low: float
    low_mid: float
    kick: float
    bass: float
    onset: float
    spectral: float
    spectral_centroid: float = 0.0


@dataclass(frozen=True)
class SpectrumConfig:
    bands: Mapping[str, tuple[float, float]]
    normalization_minimum: float
    normalization_maximum: float

    @classmethod
    def load(cls, path: Path) -> SpectrumConfig:
        with path.open("rb") as file:
            raw = tomllib.load(file)
        normalization = raw.get("normalization")
        bands = raw.get("bands")
        if not isinstance(normalization, dict) or not isinstance(bands, dict):
            raise ValueError("analysis config requires normalization and bands tables")
        minimum = _number(normalization.get("minimum"), "normalization.minimum")
        maximum = _number(normalization.get("maximum"), "normalization.maximum")
        if maximum <= minimum:
            raise ValueError("normalization.maximum must be greater than normalization.minimum")
        parsed_bands: dict[str, tuple[float, float]] = {}
        for name in FACT_NAMES:
            values = bands.get(name)
            if not isinstance(values, list) or len(values) != 2:
                raise ValueError(f"bands.{name} must contain two frequency limits")
            lower = _number(values[0], f"bands.{name}[0]")
            upper = _number(values[1], f"bands.{name}[1]")
            if upper < lower:
                raise ValueError(f"bands.{name} has inverted limits")
            parsed_bands[name] = (lower, upper)
        return cls(parsed_bands, minimum, maximum)


class SpectrumAdapter(Protocol):
    def extract(
        self, samples: Sequence[float] | np.ndarray, sample_rate: int
    ) -> Mapping[str, float]: ...


class SpectrumAnalyzer:
    def __init__(self, adapter: SpectrumAdapter, config: SpectrumConfig) -> None:
        self._adapter = adapter
        self._config = config

    def analyze(self, samples: Sequence[float] | np.ndarray, sample_rate: int) -> SpectrumFacts:
        extracted = self._adapter.extract(samples, sample_rate)
        normalized = {name: self._normalize(extracted.get(name)) for name in FACT_NAMES}
        centroid = extracted.get("spectral_centroid")
        if not isinstance(centroid, int | float) or not isfinite(centroid):
            centroid = 0.0
        normalized["spectral_centroid"] = float(centroid)
        return SpectrumFacts(**normalized)

    def _normalize(self, value: object) -> float:
        if not isinstance(value, int | float) or not isfinite(value):
            return 0.0
        minimum = self._config.normalization_minimum
        maximum = self._config.normalization_maximum
        return min(1.0, max(0.0, (float(value) - minimum) / (maximum - minimum)))


def _number(value: object, name: str) -> float:
    if not isinstance(value, int | float) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)
