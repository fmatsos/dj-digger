"""Optional semantic interpretation of immutable structural sections."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from dj_digger.analysis.segmentation import TrackSection


@dataclass(frozen=True)
class SemanticLabel:
    label: str | None
    confidence: float


class SemanticClassifier:
    """A small, injected-confidence rule classifier with no structural side effects."""

    def __init__(self, confidence: float) -> None:
        if not isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")
        self._confidence = confidence

    def classify(self, sections: tuple[TrackSection, ...]) -> tuple[SemanticLabel, ...]:
        return tuple(self._classify(section) for section in sections)

    def _classify(self, section: TrackSection) -> SemanticLabel:
        if self._confidence < 0.8:
            return SemanticLabel(None, self._confidence)
        if section.derived.bass_heavy and section.derived.stable_groove:
            return SemanticLabel("peak", self._confidence)
        if section.derived.kick_absent:
            return SemanticLabel("break", self._confidence)
        return SemanticLabel("groove", self._confidence)
