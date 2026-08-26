import weakref
from collections.abc import Mapping, Sequence
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

SPECTRUM_BANDS = {
    "sub": (20.0, 60.0),
    "low": (60.0, 250.0),
    "low_mid": (250.0, 500.0),
    "kick": (40.0, 120.0),
    "bass": (40.0, 250.0),
    "onset": (0.0, 100.0),
    "spectral": (0.0, 24_000.0),
}


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


class _CapturingRhythm(_Rhythm):
    def __init__(self) -> None:
        self.samples: object | None = None

    def analyze(self, samples: object, rate: int) -> RhythmFacts:
        self.samples = samples
        return super().analyze(samples, rate)


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


def test_composite_passes_decoded_float32_buffer_to_rhythm_without_copy(
    tmp_path: Path,
) -> None:
    from dj_digger.analysis.extractor import CompositeAudioExtractor

    decoder = _Decoder()
    decoded = decoder.decode(tmp_path / "track.wav")
    decoder.decode = lambda _path: decoded  # type: ignore[method-assign]
    rhythm = _CapturingRhythm()
    path = tmp_path / "track.wav"
    path.touch()

    CompositeAudioExtractor(
        decoder=decoder,
        probe=_Probe(),
        rhythm=rhythm,
        spectrum=_Spectrum(),
        planner=_Planner(),
    ).extract(path)

    assert rhythm.samples is decoded
    assert isinstance(rhythm.samples, np.ndarray)
    assert rhythm.samples.dtype == np.float32


def test_composite_uses_new_analyzer_identity_for_percival_beat_grid() -> None:
    from dj_digger.analysis.extractor import CompositeAudioExtractor

    assert CompositeAudioExtractor().identity.analyzer_version == "dj-digger-analysis/3"


def test_numpy_spectrum_adapter_extracts_bands_flux_and_centroid() -> None:
    adapter = NumpySpectrumAdapter(SPECTRUM_BANDS, window_size=8, hop_size=4)
    values = adapter.extract(np.sin(np.arange(32, dtype=np.float32)), 48_000)
    assert set(values) == {*SPECTRUM_BANDS, "spectral_centroid"}
    assert values["spectral_centroid"] >= 0


def _matrix_spectrum_reference(
    samples: Sequence[float] | np.ndarray,
    sample_rate: int,
    bands: Mapping[str, tuple[float, float]],
    window_size: int,
    hop_size: int,
) -> Mapping[str, float]:
    values = np.asarray(samples, dtype=np.float64)
    if values.size == 0:
        return {name: 0.0 for name in (*bands, "spectral_centroid")}
    if values.size < window_size:
        values = np.pad(values, (0, window_size - values.size))
    window = np.hanning(window_size)
    spectra = [
        np.abs(np.fft.rfft(values[start : start + window_size] * window))
        for start in range(0, values.size - window_size + 1, hop_size)
    ]
    matrix = np.asarray(spectra)
    frequencies = np.fft.rfftfreq(window_size, 1.0 / sample_rate)
    power = matrix.mean(axis=0)
    result = {}
    for name, (lower, upper) in bands.items():
        mask = (frequencies >= lower) & (frequencies <= upper)
        result[name] = float(power[mask].mean()) if np.any(mask) else 0.0
    positive_flux = np.maximum(np.diff(matrix, axis=0), 0.0)
    result["onset"] = float(positive_flux.mean()) if positive_flux.size else 0.0
    power_sum = np.sum(power)
    result["spectral_centroid"] = (
        float(np.sum(frequencies * power) / power_sum) if power_sum else 0.0
    )
    return result


@pytest.mark.parametrize(
    "samples",
    (
        np.sin(np.arange(32, dtype=np.float32)),
        np.array([0.25, -0.5, 0.75], dtype=np.float32),
        np.cos(np.arange(14, dtype=np.float32) / 3.0),
        np.array([], dtype=np.float32),
    ),
    ids=("normal", "short", "unaligned", "empty"),
)
def test_numpy_spectrum_adapter_matches_matrix_reference(samples: np.ndarray) -> None:
    actual = NumpySpectrumAdapter(SPECTRUM_BANDS, 8, 4).extract(samples, 48_000)
    expected = _matrix_spectrum_reference(samples, 48_000, SPECTRUM_BANDS, 8, 4)

    assert actual == pytest.approx(expected)


def test_numpy_spectrum_adapter_does_not_retain_all_frame_magnitudes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live = 0
    peak_live = 0
    original_abs = np.abs

    class TrackedMagnitude(np.ndarray):
        pass

    def track_abs(values: np.ndarray) -> np.ndarray:
        nonlocal live, peak_live
        magnitude = original_abs(values).view(TrackedMagnitude)
        live += 1
        peak_live = max(peak_live, live)

        def released() -> None:
            nonlocal live
            live -= 1

        weakref.finalize(magnitude, released)
        return magnitude

    monkeypatch.setattr("dj_digger.analysis.extractor.np.abs", track_abs)
    samples = np.sin(np.arange(80, dtype=np.float32))

    NumpySpectrumAdapter(SPECTRUM_BANDS, 8, 4).extract(samples, 48_000)

    assert peak_live <= 2


def test_decoder_wraps_ffmpeg_failures_with_decode_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(*_args: object, **_kwargs: object) -> object:
        raise OSError("ffmpeg missing")

    monkeypatch.setattr("dj_digger.analysis.extractor.subprocess.run", run)
    with pytest.raises(AnalysisExtractionError) as error:
        AudioDecoder().decode(Path("track.mp3"))
    assert error.value.stage == "decode"
