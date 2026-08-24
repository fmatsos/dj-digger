from dj_digger.analysis.rhythm import RhythmFacts
from dj_digger.analysis.segmentation import AnalysisFrame, Segmenter
from dj_digger.analysis.semantics import SemanticClassifier, SemanticLabel
from dj_digger.analysis.spectrum import SpectrumFacts


def structural_sections():
    frame = AnalysisFrame(
        start=0.0,
        end=8.0,
        spectrum=SpectrumFacts(0.1, 0.2, 0.3, 0.8, 0.9, 0.4, 0.5),
        rhythm=RhythmFacts(128.0, 0.9, (), 0.95, None, 0.0),
    )
    return Segmenter().segment((frame,))


def test_low_confidence_semantic_label_is_absent() -> None:
    labels = SemanticClassifier(confidence=0.79).classify(structural_sections())

    assert labels == (SemanticLabel(label=None, confidence=0.79),)


def test_semantic_classification_never_changes_structural_sections() -> None:
    sections = structural_sections()

    labels = SemanticClassifier(confidence=0.8).classify(sections)

    assert labels == (SemanticLabel(label="peak", confidence=0.8),)
    assert sections == structural_sections()
