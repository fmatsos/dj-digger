from pathlib import Path

import numpy as np
import pytest

from dj_digger.analysis.audio import TechnicalAudioMetadata
from dj_digger.analysis.extractor import (
    AnalysisExtractionError,
    AnalysisExtractionResult,
    AudioDecoder,
    NumpySpectrumAdapter,
)
from dj_digger.analysis.rhythm import RhythmFacts
from dj_digger.analysis.spectrum import SpectrumFacts
from dj_digger.analysis.windows import IntroOutroWindows


def test_extraction_result_has_only_public_status_fields() -> None:
    result = AnalysisExtractionResult({}, {}, None, "succeeded")
    assert result.status == "succeeded"
    assert not hasattr(result, "error")
    assert not hasattr(result, "stage")


def test_extraction_error_stage_is_typed_literal() -> None:
    error = AnalysisExtractionError("spectrum", "failed")
    assert error.stage == "spectrum"


class _Decoder:
    def decode(self, _path: Path) -> np.ndarray:
        return np.ones(48_000, dtype=np.float32)


class _Probe:
    def probe(self, _path: Path) -> TechnicalAudioMetadata:
        return TechnicalAudioMetadata(
            1.0, 48_000, 1, "pcm_s16le", "wav", None, True, None, None, None
        )


class _Rhythm:
    def analyze(self, _samples: object, _rate: int) -> RhythmFacts:
        return RhythmFacts(120.0, 0.9, tuple(i * 0.5 for i in range(100)), 0.9, "C major", 0.9)


class _Spectrum:
    def analyze(self, _samples: object, _rate: int) -> SpectrumFacts:
        return SpectrumFacts(0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1_000.0)


class _Planner:
    def plan(self, _beats: object) -> dict[int, IntroOutroWindows]:
        return {bars: IntroOutroWindows(None, None) for bars in (8, 16, 32, 64)}


class _Fail:
    def __init__(self, stage: str) -> None:
        self.stage = stage

    def decode(self, _path: Path) -> np.ndarray:
        raise RuntimeError("controlled failure")

    def probe(self, _path: Path) -> TechnicalAudioMetadata:
        raise RuntimeError("controlled failure")

    def analyze(self, _samples: object, _rate: int) -> object:
        raise RuntimeError("controlled failure")

    def plan(self, _beats: object) -> object:
        raise RuntimeError("controlled failure")

    def segment(self, _frames: object) -> object:
        raise RuntimeError("controlled failure")

    def classify(self, _sections: object) -> object:
        raise RuntimeError("controlled failure")


@pytest.mark.parametrize(
    "stage",
    (
        "decode", "technical", "rhythm", "spectrum", "windows", "segmentation",
        "semantics", "aggregation",
    ),
)
def test_composite_reports_each_stage(stage: str, tmp_path: Path) -> None:
    from dj_digger.analysis.extractor import CompositeAudioExtractor

    common = {
        "decoder": _Decoder(), "probe": _Probe(), "rhythm": _Rhythm(),
        "spectrum": _Spectrum(), "planner": _Planner(),
    }
    failing = _Fail(stage)
    if stage == "decode":
        common["decoder"] = failing
    elif stage == "technical":
        common["probe"] = failing
    elif stage == "rhythm":
        common["rhythm"] = failing
    elif stage == "spectrum":
        common["spectrum"] = failing
    elif stage == "windows":
        common["planner"] = failing
    elif stage == "segmentation":
        common["segmenter"] = failing
    elif stage == "semantics":
        common["semantics"] = failing
    with pytest.raises(AnalysisExtractionError) as raised:
        CompositeAudioExtractor(**common).extract(tmp_path / "missing.wav")
    assert raised.value.stage == stage


def test_decoder_builds_float32_mono_48khz_without_tempfile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: object) -> object:
        calls.append(argv)
        assert kwargs["capture_output"] is True
        return type("Result", (), {"stdout": np.array([0.25, -0.5], dtype="<f4").tobytes()})()

    monkeypatch.setattr("dj_digger.analysis.extractor.subprocess.run", run)
    samples = AudioDecoder().decode(Path("track.mp3"))
    assert samples.dtype == np.float32
    assert samples.tolist() == [0.25, -0.5]
    assert calls[0][3:] == ["-i", "track.mp3", "-f", "f32le", "-ac", "1", "-ar", "48000", "pipe:1"]


def test_numpy_spectrum_adapter_extracts_bands_flux_and_centroid() -> None:
    config = {"sub": (20.0, 60.0), "low": (60.0, 250.0), "low_mid": (250.0, 500.0),
              "kick": (40.0, 120.0), "bass": (40.0, 250.0), "onset": (0.0, 100.0),
              "spectral": (0.0, 24000.0)}
    adapter = NumpySpectrumAdapter(config, window_size=8, hop_size=4)
    values = adapter.extract(np.sin(np.arange(32, dtype=np.float32)), 48_000)
    assert set(values) == {*config, "spectral_centroid"}
    assert values["spectral_centroid"] >= 0


def test_decoder_wraps_ffmpeg_failures_with_decode_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(*_args: object, **_kwargs: object) -> object:
        raise OSError("ffmpeg missing")

    monkeypatch.setattr("dj_digger.analysis.extractor.subprocess.run", run)
    with pytest.raises(AnalysisExtractionError) as error:
        AudioDecoder().decode(Path("track.mp3"))
    assert error.value.stage == "decode"
