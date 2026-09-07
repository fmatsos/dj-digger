"""Deterministic beat-anchored intro and outro windows for DJ transitions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

WINDOW_BARS = (8, 16, 32, 64)


@dataclass(frozen=True)
class BeatWindow:
    start: float
    end: float


@dataclass(frozen=True)
class IntroOutroWindows:
    intro: BeatWindow | None
    outro: BeatWindow | None


class DjWindowPlanner:
    def __init__(self, beats_per_bar: int = 4) -> None:
        if beats_per_bar <= 0:
            raise ValueError("beats_per_bar must be positive")
        self._beats_per_bar = beats_per_bar

    def plan(self, beats: Sequence[float]) -> Mapping[int, IntroOutroWindows]:
        stable_beats = tuple(float(beat) for beat in beats if isfinite(beat))
        return {bars: self._for_bars(stable_beats, bars) for bars in WINDOW_BARS}

    def _for_bars(self, beats: tuple[float, ...], bars: int) -> IntroOutroWindows:
        beat_count = bars * self._beats_per_bar
        if len(beats) < beat_count + 1:
            return IntroOutroWindows(None, None)
        return IntroOutroWindows(
            intro=BeatWindow(beats[0], beats[beat_count]),
            outro=BeatWindow(beats[-beat_count - 1], beats[-1]),
        )
