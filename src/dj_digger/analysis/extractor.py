"""Composite, read-only audio analysis extraction primitives."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Literal, TypeVar

import numpy as np

from dj_digger.analysis.audio import TechnicalAudioMetadata
from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.analysis.ffmpeg import FFmpegProbe
from dj_digger.analysis.rhythm import RhythmAnalyzer, RhythmFacts
from dj_digger.analysis.segmentation import AnalysisFrame, Segmenter, TrackSection
from dj_digger.analysis.semantics import SemanticClassifier, SemanticLabel
from dj_digger.analysis.spectrum import (
    FACT_NAMES,
    SpectrumAnalyzer,
    SpectrumConfig,
    SpectrumFacts,
)
from dj_digger.analysis.windows import DjWindowPlanner, IntroOutroWindows
from dj_digger.config import DspConfig

Stage = Literal[
    "decode",
    "technical",
    "rhythm",
    "spectrum",
    "windows",
    "segmentation",
    "semantics",
    "aggregation",
]
ResultStatus = Literal["succeeded", "partial", "failed"]


class AnalysisExtractionError(RuntimeError):
    def __init__(self, stage: Stage, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.cause = cause

T = TypeVar("T")


class AudioDecoder:
    """Decode through FFmpeg stdout; no temporary or library output is written."""

    def __init__(self, ffmpeg: str = "ffmpeg") -> None:
        self._ffmpeg = ffmpeg

    def decode(self, path: Path) -> np.ndarray:
        argv = [
            self._ffmpeg, "-v", "error", "-i", str(path), "-f", "f32le",
            "-ac", "1", "-ar", "48000", "pipe:1",
        ]
        try:
            result = subprocess.run(argv, check=True, capture_output=True)
            raw = result.stdout if isinstance(result.stdout, bytes) else bytes(result.stdout)
            if not raw or len(raw) % 4:
                raise ValueError("ffmpeg returned an empty or incomplete float32 stream")
            return np.frombuffer(raw, dtype="<f4").copy()
        except Exception as error:
            raise AnalysisExtractionError("decode", "audio decoding failed", error) from error


class NumpySpectrumAdapter:
    """Hann-windowed rFFT adapter producing configured energies, flux and centroid."""

    def __init__(
        self,
        bands: Mapping[str, tuple[float, float]],
        window_size: int = 4096,
        hop_size: int = 2048,
    ) -> None:
        self._bands = bands
        self._window_size = window_size
        self._hop_size = hop_size

    def extract(
        self, samples: Sequence[float] | np.ndarray, sample_rate: int
    ) -> Mapping[str, float]:
        values = np.asarray(samples, dtype=np.float64)
        if values.size == 0:
            return {name: 0.0 for name in (*FACT_NAMES, "spectral_centroid")}
        if values.size < self._window_size:
            values = np.pad(values, (0, self._window_size - values.size))
        window = np.hanning(self._window_size)
        spectra = []
        for start in range(0, values.size - self._window_size + 1, self._hop_size):
            spectra.append(np.abs(np.fft.rfft(values[start : start + self._window_size] * window)))
        matrix = np.asarray(spectra)
        frequencies = np.fft.rfftfreq(self._window_size, 1.0 / sample_rate)
        power = matrix.mean(axis=0)
        result: dict[str, float] = {}
        for name, (lower, upper) in self._bands.items():
            mask = (frequencies >= lower) & (frequencies <= upper)
            result[name] = float(power[mask].mean()) if np.any(mask) else 0.0
        positive_flux = np.maximum(np.diff(matrix, axis=0), 0.0)
        result["onset"] = float(positive_flux.mean()) if positive_flux.size else 0.0
        result["spectral_centroid"] = (
            float(np.sum(frequencies * power) / np.sum(power)) if np.sum(power) else 0.0
        )
        return result


@dataclass(frozen=True)
class AnalysisExtractionResult:
    payload: Mapping[str, object]
    sections: Mapping[str, object]
    confidence: float | None
    status: ResultStatus


class CompositeAudioExtractor:
    """Compose decode, technical, rhythm, spectrum, windows, sections and semantics."""

    def __init__(
        self,
        config: DspConfig | None = None,
        *,
        decoder: AudioDecoder | None = None,
        probe: FFmpegProbe | None = None,
        rhythm: RhythmAnalyzer | None = None,
        spectrum: SpectrumAnalyzer | None = None,
        planner: DjWindowPlanner | None = None,
        segmenter: Segmenter | None = None,
        semantics: SemanticClassifier | None = None,
    ) -> None:
        dsp = config if config is not None else DspConfig.canonical()
        self.identity = AnalysisIdentity(2, "dj-digger-analysis/2", dsp.config_hash)
        self._decoder = decoder or AudioDecoder()
        self._probe = probe or FFmpegProbe()
        self._rhythm = rhythm or RhythmAnalyzer()
        adapter = NumpySpectrumAdapter(dsp.bands, dsp.fft_window_size, dsp.fft_hop_size)
        self._spectrum = spectrum or SpectrumAnalyzer(
            adapter, SpectrumConfig(dsp.bands, 0.0, 100.0)
        )
        self._planner = planner or DjWindowPlanner()
        self._segmenter = segmenter or Segmenter(dsp.segmentation_min_seconds)
        self._semantics = semantics or SemanticClassifier(dsp.semantic_min_confidence)

    def extract(
        self, path: Path, *, source_id: str = "source", track_id: int = 1,
        relative_path: str | None = None
    ) -> AnalysisExtractionResult:
        try:
            samples = self._stage("decode", lambda: self._decoder.decode(path))
            technical = self._stage("technical", lambda: self._probe.probe(path))
            rhythm = self._stage(
                "rhythm", lambda: self._rhythm.analyze(samples.astype(np.float64), 48_000)
            )
            spectrum = self._stage("spectrum", lambda: self._spectrum.analyze(samples, 48_000))
            windows = self._stage("windows", lambda: self._planner.plan(rhythm.beat_positions))
            frames = self._stage("spectrum", lambda: self._frames(samples, rhythm))
            sections = self._stage("segmentation", lambda: self._segmenter.segment(frames))
            labels = self._stage("semantics", lambda: self._semantics.classify(sections))
            payload = self._stage(
                "aggregation",
                lambda: self._payload(
                    path, source_id, track_id, technical, rhythm, spectrum, windows, samples,
                    relative_path,
                ),
            )
            rows = tuple(
                self._section_row(i, s, labels[i], rhythm)
                for i, s in enumerate(sections)
            )
            section_doc = {
                "source_id": source_id, "track_id": track_id, "path": relative_path or str(path),
                "analysis_schema_version": 2, "sections": list(rows),
            }
            return AnalysisExtractionResult(
                payload, section_doc, self._confidence(rhythm, labels), "succeeded"
            )
        except AnalysisExtractionError:
            raise
        except Exception as error:
            raise AnalysisExtractionError("aggregation", str(error), error) from error

    @staticmethod
    def _stage(stage: Stage, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except AnalysisExtractionError:
            raise
        except Exception as error:
            raise AnalysisExtractionError(stage, f"{stage} stage failed", error) from error

    def _frames(self, samples: np.ndarray, rhythm: RhythmFacts) -> tuple[AnalysisFrame, ...]:
        duration = len(samples) / 48_000
        step = min(16.0, duration) or 1.0
        frames = []
        for start in np.arange(0.0, duration, step):
            end = min(start + step, duration)
            left, right = int(start * 48_000), int(end * 48_000)
            facts = self._spectrum.analyze(samples[left:right], 48_000)
            frames.append(AnalysisFrame(float(start), float(end), facts, rhythm))
        return tuple(frames)

    def _payload(
        self,
        path: Path,
        source_id: str,
        track_id: int,
        technical: TechnicalAudioMetadata,
        rhythm: RhythmFacts,
        spectrum: SpectrumFacts,
        windows: Mapping[int, IntroOutroWindows],
        samples: np.ndarray,
        relative_path: str | None,
    ) -> dict[str, object]:
        stat = path.stat()
        payload: dict[str, object] = {
            "source_id": source_id, "track_id": track_id, "path": relative_path or str(path),
            "size_bytes": stat.st_size, "mtime": stat.st_mtime_ns, "analysis_schema_version": 2,
            "analyzer_version": self.identity.analyzer_version,
            "config_hash": self.identity.config_hash,
            "analysis_status": "ok", "analysis_confidence": rhythm.bpm_confidence,
            "duration_seconds": technical.duration_seconds,
            "sample_rate": technical.sample_rate or 48000,
            "channels": technical.channels or 1, "codec": technical.codec,
            "container": technical.container, "lossless": technical.lossless,
            "bpm": rhythm.bpm, "bpm_confidence": rhythm.bpm_confidence,
            "beat_stability": rhythm.beat_stability, "key": rhythm.key,
            "key_confidence": rhythm.key_confidence,
            "loudness_lufs": technical.loudness_lufs, "true_peak_db": technical.true_peak_db,
            "dynamic_range": technical.dynamic_range, "sub_energy": spectrum.sub,
            "low_energy": spectrum.low, "low_mid_energy": spectrum.low_mid,
            "kick_strength": spectrum.kick, "kick_density": spectrum.kick,
            "bass_density": spectrum.bass, "onset_density": spectrum.onset,
            "spectral_centroid": spectrum.spectral_centroid,
        }
        for side in ("intro", "outro"):
            for bars in (8, 16, 32, 64):
                payload.update({
                    f"{side}_{bars}_available": False,
                    **{f"{side}_{bars}_{name}": None for name in (
                        "bpm", "beat_stability", "sub_energy", "low_energy", "low_mid_energy",
                        "kick_strength", "kick_density", "bass_density", "loudness_lufs",
                        "onset_density", "spectral_centroid",
                    )},
                })
        stable = rhythm.bpm is not None and rhythm.beat_stability >= 0.8
        for bars, window in windows.items():
            for side, interval in (("intro", window.intro), ("outro", window.outro)):
                if interval is None or not stable:
                    continue
                prefix = f"{side}_{bars}_"
                local = self._spectrum.analyze(
                    samples[int(interval.start * 48000):int(interval.end * 48000)], 48000
                )
                payload.update({
                    prefix + "available": True, prefix + "bpm": rhythm.bpm,
                    prefix + "beat_stability": rhythm.beat_stability,
                    prefix + "sub_energy": local.sub, prefix + "low_energy": local.low,
                    prefix + "low_mid_energy": local.low_mid,
                    prefix + "kick_strength": local.kick, prefix + "kick_density": local.kick,
                    prefix + "bass_density": local.bass,
                    prefix + "loudness_lufs": technical.loudness_lufs,
                    prefix + "onset_density": local.onset,
                    prefix + "spectral_centroid": local.spectral_centroid,
                })
        return payload

    def _section_row(
        self, index: int, section: TrackSection, label: SemanticLabel, rhythm: RhythmFacts
    ) -> dict[str, object]:
        s = section
        facts = s.facts
        bpm = rhythm.bpm
        if bpm is not None and rhythm.beat_stability >= 0.8:
            bar_duration = 60.0 / bpm * 4.0
            start_bar = int(s.start / bar_duration) + 1
            end_bar = max(start_bar, int(ceil(s.end / bar_duration)))
        else:
            start_bar = None
            end_bar = None
        bars = (
            max(1, end_bar - start_bar + 1)
            if end_bar is not None and start_bar is not None
            else None
        )
        facts_doc = {
            "bpm": facts.bpm, "beat_stability": facts.beat_stability,
            "kick_present": not s.derived.kick_absent, "kick_strength": facts.kick_strength,
            "kick_density": facts.kick_strength, "bass_density": facts.bass_energy,
            "sub_energy": facts.sub_energy, "low_energy": facts.low_energy,
            "low_mid_energy": facts.low_mid_energy, "loudness_lufs": None,
            "onset_density": facts.onset_energy, "spectral_centroid": facts.spectral_centroid,
            "energy_slope": 1.0 if s.derived.energy_rising else -1.0
            if s.derived.energy_falling else 0.0,
        }
        return {
            "index": index, "start_seconds": s.start, "end_seconds": s.end,
            "start_bar": start_bar, "end_bar": end_bar, "bars": bars,
            "facts": facts_doc, "derived": s.derived.__dict__,
            "semantic": {"label": label.label, "confidence": label.confidence},
            "transition_suitability_in": label.confidence,
            "transition_suitability_out": label.confidence,
        }

    @staticmethod
    def _confidence(rhythm: RhythmFacts, labels: Sequence[SemanticLabel]) -> float:
        return float(rhythm.bpm_confidence)
