from __future__ import annotations

import importlib
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

Samples = NDArray[np.float32]


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


class TempoAdapter(Protocol):
    def extract(self, samples: Samples, sample_rate: int) -> float: ...


class BeatGridAdapter(Protocol):
    def extract(
        self, samples: Samples, sample_rate: int, bpm: float
    ) -> tuple[tuple[float, ...], float, tuple[float, ...]]: ...


class EssentiaTempoAdapter:
    def extract(self, samples: Samples, sample_rate: int) -> float:
        try:
            es = _load_essentia_standard()
        except ImportError as error:
            raise RuntimeError("Essentia is required for tempo analysis") from error

        return float(es.PercivalBpmEstimator(sampleRate=sample_rate)(samples))


class EssentiaBeatGridAdapter:
    _FRAME_SIZE = 1024
    _HOP_SIZE = 512

    def extract(
        self, samples: Samples, sample_rate: int, bpm: float
    ) -> tuple[tuple[float, ...], float, tuple[float, ...]]:
        try:
            es = _load_essentia_standard()
        except ImportError as error:
            raise RuntimeError("Essentia is required for beat-grid analysis") from error

        window = es.Windowing(type="hann")
        fft = es.FFT()
        cartesian_to_polar = es.CartesianToPolar()
        onset = es.OnsetDetection(method="complex")
        novelty = []
        for frame in es.FrameGenerator(samples, frameSize=self._FRAME_SIZE, hopSize=self._HOP_SIZE):
            magnitude, phase = cartesian_to_polar(fft(window(frame)))
            novelty.append(float(onset(magnitude, phase)))

        outputs = es.BpmHistogram(
            frameRate=sample_rate / self._HOP_SIZE,
            bpm=bpm,
            constantTempo=True,
            minBpm=50,
            maxBpm=210,
        )(np.asarray(novelty, dtype=np.float32))
        beats = tuple(float(position) for position in outputs[5])
        intervals = tuple(right - left for left, right in zip(beats, beats[1:], strict=False))
        return beats, _beat_stability(intervals), intervals


class EssentiaRhythmAdapter:
    def __init__(
        self,
        tempo_adapter: TempoAdapter | None = None,
        beat_grid_adapter: BeatGridAdapter | None = None,
    ) -> None:
        self._tempo_adapter = tempo_adapter or EssentiaTempoAdapter()
        self._beat_grid_adapter = beat_grid_adapter or EssentiaBeatGridAdapter()

    def extract(
        self, samples: Samples, sample_rate: int
    ) -> tuple[float, tuple[float, ...], float, tuple[float, ...]]:
        bpm = self._tempo_adapter.extract(samples, sample_rate)
        beats, confidence, intervals = self._beat_grid_adapter.extract(samples, sample_rate, bpm)
        return bpm, beats, confidence, intervals


class EssentiaKeyAdapter:
    def extract(self, samples: Samples, sample_rate: int) -> tuple[str, str, float]:
        try:
            es = _load_essentia_standard()
        except ImportError as error:
            raise RuntimeError("Essentia is required for key analysis") from error

        key, scale, confidence = es.KeyExtractor(sampleRate=sample_rate)(samples)
        return str(key), str(scale), float(confidence)


def _disable_essentia_native_info_warning(essentia: object) -> None:
    """Keep native errors while silencing Essentia's noisy info/warning stream."""
    log = getattr(essentia, "log", None)
    if log is None or not all(
        hasattr(log, name) for name in ("infoActive", "warningActive", "errorActive")
    ):
        raise RuntimeError("Essentia logging controls are unavailable")
    log.infoActive = False
    log.warningActive = False
    log.errorActive = True


def _load_essentia_standard() -> Any:
    """Configure native logging before loading Essentia's standard algorithms."""
    essentia = importlib.import_module("essentia")
    _disable_essentia_native_info_warning(essentia)
    return importlib.import_module("essentia.standard")


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
