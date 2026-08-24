"""Deterministic structural sections built from timed audio facts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from statistics import fmean

from dj_digger.analysis.rhythm import RhythmFacts
from dj_digger.analysis.spectrum import SpectrumFacts


@dataclass(frozen=True)
class AnalysisFrame:
    """A timed, independently extracted set of audio facts."""

    start: float
    end: float
    spectrum: SpectrumFacts
    rhythm: RhythmFacts


@dataclass(frozen=True)
class SectionFacts:
    bpm: float | None
    beat_stability: float
    kick_strength: float
    bass_energy: float
    sub_energy: float
    low_energy: float
    low_mid_energy: float
    onset_energy: float
    spectral_energy: float
    spectral_centroid: float = 0.0


@dataclass(frozen=True)
class SectionDerived:
    percussion_only: bool
    bass_light: bool
    bass_heavy: bool
    energy_rising: bool
    energy_falling: bool
    stable_groove: bool
    kick_absent: bool


@dataclass(frozen=True)
class TrackSection:
    start: float
    end: float
    facts: SectionFacts
    derived: SectionDerived


class Segmenter:
    """Groups adjacent analysis frames into fixed, reproducible time sections."""

    def __init__(self, section_duration: float = 16.0) -> None:
        if not isfinite(section_duration) or section_duration <= 0.0:
            raise ValueError("section_duration must be a positive finite number")
        self._section_duration = section_duration

    def segment(self, frames: Iterable[AnalysisFrame]) -> tuple[TrackSection, ...]:
        ordered = tuple(frames)
        if not ordered:
            return ()
        self._validate(ordered)
        sections: list[TrackSection] = []
        current: list[AnalysisFrame] = []
        boundary = ordered[0].start + self._section_duration
        for frame in ordered:
            if current and frame.start >= boundary:
                sections.append(self._make_section(current))
                current = []
                boundary = frame.start + self._section_duration
            current.append(frame)
        sections.append(self._make_section(current))
        return tuple(sections)

    @staticmethod
    def _validate(frames: tuple[AnalysisFrame, ...]) -> None:
        previous_end = frames[0].start
        for frame in frames:
            if not isfinite(frame.start) or not isfinite(frame.end) or frame.end <= frame.start:
                raise ValueError("frames must have finite, increasing boundaries")
            if frame.start != previous_end:
                raise ValueError("frames must be contiguous")
            previous_end = frame.end

    def _make_section(self, frames: list[AnalysisFrame]) -> TrackSection:
        facts = SectionFacts(
            bpm=_mean_optional(frame.rhythm.bpm for frame in frames),
            beat_stability=_mean(frame.rhythm.beat_stability for frame in frames),
            kick_strength=_mean(frame.spectrum.kick for frame in frames),
            bass_energy=_mean(frame.spectrum.bass for frame in frames),
            sub_energy=_mean(frame.spectrum.sub for frame in frames),
            low_energy=_mean(frame.spectrum.low for frame in frames),
            low_mid_energy=_mean(frame.spectrum.low_mid for frame in frames),
            onset_energy=_mean(frame.spectrum.onset for frame in frames),
            spectral_energy=_mean(frame.spectrum.spectral for frame in frames),
            spectral_centroid=_mean(frame.spectrum.spectral_centroid for frame in frames),
        )
        energies = tuple(
            frame.spectrum.sub + frame.spectrum.low + frame.spectrum.bass for frame in frames
        )
        derived = SectionDerived(
            percussion_only=facts.kick_strength > 0.0 and facts.bass_energy < 0.1,
            bass_light=facts.bass_energy < 0.1,
            bass_heavy=facts.bass_energy >= 0.7,
            energy_rising=energies[-1] > energies[0],
            energy_falling=energies[-1] < energies[0],
            stable_groove=facts.beat_stability >= 0.8,
            kick_absent=facts.kick_strength == 0.0,
        )
        return TrackSection(frames[0].start, frames[-1].end, facts, derived)


def _mean(values: Iterable[float]) -> float:
    return fmean(values)


def _mean_optional(values: Iterable[float | None]) -> float | None:
    finite = tuple(value for value in values if value is not None and isfinite(value))
    return fmean(finite) if finite else None
