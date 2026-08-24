from dataclasses import replace
from pathlib import Path

from dj_digger.analysis.spectrum import SpectrumAnalyzer, SpectrumConfig, SpectrumFacts


class StubSpectrumAdapter:
    def extract(self, _samples, _sample_rate):
        return {
            "sub": -10.0,
            "low": 5.0,
            "low_mid": 20.0,
            "kick": 40.0,
            "bass": float("nan"),
            "onset": 50.0,
            "spectral": 100.0,
        }


def config() -> SpectrumConfig:
    return SpectrumConfig.load(Path(__file__).parents[1] / "config" / "analysis.toml")


def test_normalizes_spectral_facts_and_rejects_non_finite_values() -> None:
    facts = SpectrumAnalyzer(StubSpectrumAdapter(), config()).analyze([], 44_100)

    assert facts == SpectrumFacts(
        sub=0.0,
        low=0.05,
        low_mid=0.2,
        kick=0.4,
        bass=0.0,
        onset=0.5,
        spectral=1.0,
    )


def test_normalization_limits_come_from_injected_config() -> None:
    injected = replace(config(), normalization_minimum=0.0, normalization_maximum=200.0)

    facts = SpectrumAnalyzer(StubSpectrumAdapter(), injected).analyze([], 44_100)

    assert facts.low == 0.025


def test_frequency_bands_are_loaded_from_versioned_config() -> None:
    loaded = config()

    assert loaded.bands["sub"] == (20.0, 60.0)
    assert loaded.bands["low_mid"] == (250.0, 500.0)
