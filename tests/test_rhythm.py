from dataclasses import asdict

import numpy as np
import pytest

from dj_digger.analysis.rhythm import RhythmAnalyzer


class FixedRhythmAdapter:
    def extract(
        self, samples: np.ndarray, sample_rate: int
    ) -> tuple[float, tuple[float, ...], float, tuple[float, ...]]:
        assert samples.shape == (2048,)
        assert sample_rate == 48_000
        return 145.2, (0.0, 0.413, 0.826, 1.239), 0.82, (0.413, 0.413, 0.413)


class FixedKeyAdapter:
    def extract(self, samples: np.ndarray, sample_rate: int) -> tuple[str, str, float]:
        assert samples.shape == (2048,)
        assert sample_rate == 48_000
        return "c", "minor", 0.91


def analyzer() -> RhythmAnalyzer:
    return RhythmAnalyzer(rhythm_adapter=FixedRhythmAdapter(), key_adapter=FixedKeyAdapter())


def test_rhythm_facts_are_within_bpm_tolerance_and_bounded() -> None:
    facts = analyzer().analyze(np.zeros(2048), 48_000)

    assert facts.bpm == pytest.approx(145.0, abs=0.5)
    assert facts.bpm_confidence == pytest.approx(0.82)
    assert facts.beat_positions == (0.0, 0.413, 0.826, 1.239)
    assert 0.0 <= facts.beat_stability <= 1.0
    assert facts.key == "C minor"
    assert facts.key_confidence == pytest.approx(0.91)


def test_rhythm_analysis_is_repeatably_deterministic() -> None:
    samples = np.zeros(2048)

    assert analyzer().analyze(samples, 48_000) == analyzer().analyze(samples, 48_000)


def test_no_beats_normalizes_to_empty_rhythm_facts() -> None:
    class NoBeatsAdapter:
        def extract(
            self, samples: np.ndarray, sample_rate: int
        ) -> tuple[float, tuple[float, ...], float, tuple[float, ...]]:
            return 128.0, (), 0.8, ()

    facts = RhythmAnalyzer(rhythm_adapter=NoBeatsAdapter(), key_adapter=FixedKeyAdapter()).analyze(
        np.zeros(2048), 48_000
    )

    assert facts.bpm is None
    assert facts.bpm_confidence == 0.0
    assert facts.beat_positions == ()
    assert facts.beat_stability == 0.0


def test_adapter_error_is_reported_with_stage_context() -> None:
    class BrokenRhythmAdapter:
        def extract(self, samples: np.ndarray, sample_rate: int) -> tuple[
            float, tuple[float, ...], float, tuple[float, ...]
        ]:
            raise ValueError("bad audio")

    with pytest.raises(RuntimeError, match="rhythm adapter failed"):
        RhythmAnalyzer(rhythm_adapter=BrokenRhythmAdapter(), key_adapter=FixedKeyAdapter()).analyze(
            np.zeros(2048), 48_000
        )


def test_rhythm_facts_do_not_produce_semantic_labels() -> None:
    fields = asdict(analyzer().analyze(np.zeros(2048), 48_000))

    assert set(fields) == {
        "bpm",
        "bpm_confidence",
        "beat_positions",
        "beat_stability",
        "key",
        "key_confidence",
    }
