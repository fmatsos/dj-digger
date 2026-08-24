from dj_digger.analysis.rhythm import RhythmFacts
from dj_digger.analysis.segmentation import AnalysisFrame, SectionFacts, Segmenter
from dj_digger.analysis.spectrum import SpectrumFacts


def frame(start: float, end: float, *, bass: float = 0.2, kick: float = 0.5) -> AnalysisFrame:
    return AnalysisFrame(
        start=start,
        end=end,
        spectrum=SpectrumFacts(0.1, 0.2, 0.3, kick, bass, 0.4, 0.5),
        rhythm=RhythmFacts(128.0, 0.9, (), 0.95, None, 0.0),
    )


def test_segmenter_creates_deterministic_contiguous_sections_with_aggregated_facts() -> None:
    sections = Segmenter().segment((frame(0.0, 8.0), frame(8.0, 16.0), frame(16.0, 24.0)))

    assert [(section.start, section.end) for section in sections] == [
        (0.0, 16.0),
        (16.0, 24.0),
    ]
    assert sections[0].facts == SectionFacts(
        bpm=128.0,
        beat_stability=0.95,
        kick_strength=0.5,
        bass_energy=0.2,
        sub_energy=0.1,
        low_energy=0.2,
        low_mid_energy=0.3,
        onset_energy=0.4,
        spectral_energy=0.5,
    )


def test_segmenter_derives_structural_flags_from_aggregated_facts() -> None:
    section = Segmenter().segment((frame(0.0, 8.0, bass=0.05, kick=0.0),))[0]

    assert section.derived.kick_absent is True
    assert section.derived.percussion_only is False
    assert section.derived.bass_light is True
    assert section.derived.bass_heavy is False
    assert section.derived.stable_groove is True
