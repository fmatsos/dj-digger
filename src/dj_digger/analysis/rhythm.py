from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

Samples = NDArray[np.float64]


@dataclass(frozen=True)
class RhythmFacts:
    bpm: float | None
    bpm_confidence: float
    beat_positions: tuple[float, ...]
    beat_stability: float
    key: str | None
    key_confidence: float


class RhythmAdapter(Protocol):
    def extract(
        self, samples: Samples, sample_rate: int
    ) -> tuple[float, tuple[float, ...], float, tuple[float, ...]]: ...


class KeyAdapter(Protocol):
    def extract(self, samples: Samples, sample_rate: int) -> tuple[str, str, float]: ...


class EssentiaRhythmAdapter:
    def extract(
        self, samples: Samples, sample_rate: int
    ) -> tuple[float, tuple[float, ...], float, tuple[float, ...]]:
        try:
            import essentia.standard as es  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("Essentia is required for rhythm analysis") from error

        bpm, beats, confidence, _estimates, intervals = es.RhythmExtractor2013(
            method="multifeature"
        )(samples)
        return float(bpm), tuple(float(beat) for beat in beats), float(confidence), tuple(
            float(interval) for interval in intervals
        )


class EssentiaKeyAdapter:
    def extract(self, samples: Samples, sample_rate: int) -> tuple[str, str, float]:
        try:
            import essentia.standard as es
        except ImportError as error:
            raise RuntimeError("Essentia is required for key analysis") from error

        key, scale, confidence = es.KeyExtractor(sampleRate=sample_rate)(samples)
        return str(key), str(scale), float(confidence)


class RhythmAnalyzer:
    def __init__(
        self,
        rhythm_adapter: RhythmAdapter | None = None,
        key_adapter: KeyAdapter | None = None,
    ) -> None:
        self._rhythm_adapter = rhythm_adapter or EssentiaRhythmAdapter()
        self._key_adapter = key_adapter or EssentiaKeyAdapter()

    def analyze(self, samples: Samples, sample_rate: int) -> RhythmFacts:
        try:
            bpm, beat_positions, bpm_confidence, intervals = self._rhythm_adapter.extract(
                samples, sample_rate
            )
        except Exception as error:
            raise RuntimeError("rhythm adapter failed") from error

        normalized_beats = tuple(position for position in beat_positions if isfinite(position))
        if not normalized_beats:
            return RhythmFacts(None, 0.0, (), 0.0, *self._key_facts(samples, sample_rate))

        return RhythmFacts(
            _finite_or_none(bpm),
            _bounded(bpm_confidence),
            normalized_beats,
            _beat_stability(intervals),
            *self._key_facts(samples, sample_rate),
        )

    def _key_facts(self, samples: Samples, sample_rate: int) -> tuple[str | None, float]:
        try:
            key, scale, confidence = self._key_adapter.extract(samples, sample_rate)
        except Exception as error:
            raise RuntimeError("key adapter failed") from error
        return _canonical_key(key, scale), _bounded(confidence)


def _finite_or_none(value: float) -> float | None:
    return value if isfinite(value) else None


def _bounded(value: float) -> float:
    if not isfinite(value):
        return 0.0
    return min(1.0, max(0.0, value))


def _beat_stability(intervals: tuple[float, ...]) -> float:
    finite_intervals = tuple(
        interval for interval in intervals if isfinite(interval) and interval > 0.0
    )
    if not finite_intervals:
        return 0.0
    mean = sum(finite_intervals) / len(finite_intervals)
    variance = sum((interval - mean) ** 2 for interval in finite_intervals) / len(finite_intervals)
    return _bounded(1.0 - sqrt(variance) / mean)


def _canonical_key(key: str, scale: str) -> str | None:
    normalized_key = key.strip().upper()
    normalized_scale = scale.strip().lower()
    if normalized_key not in {"A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#"}:
        return None
    if normalized_scale not in {"major", "minor"}:
        return None
    return f"{normalized_key} {normalized_scale}"
