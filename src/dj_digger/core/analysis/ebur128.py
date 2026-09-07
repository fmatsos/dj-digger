"""Bounded, read-only FFmpeg EBU R128 analysis."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dj_digger.duplicates.mastering import MasteringMeasurements, derive_mastering_measurements

_MAX_DIAGNOSTICS = 8_192
_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


class EbuR128AnalysisError(RuntimeError):
    """A classified failure while running or parsing FFmpeg."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(message[:_MAX_DIAGNOSTICS])


@dataclass(frozen=True)
class _ParsedSummary:
    integrated: float | None
    lra: float | None
    peak: float | None


def _number(value: str) -> float | None:
    try:
        number = float(value)
    except ValueError:
        return None
    return number if number not in (float("inf"), float("-inf")) else None


def _summary(output: str) -> _ParsedSummary:
    def find(label: str) -> float | None:
        match = re.search(rf"(?:^|\n)\s*{label}:\s*({_NUMBER}|[-+]?inf)", output, re.I)
        return _number(match.group(1)) if match else None

    return _ParsedSummary(find("I"), find("LRA"), find("Peak"))


def parse_ebur128_output(output: str) -> MasteringMeasurements:
    """Parse structured metadata and the final human-readable EBU summary.

    FFmpeg emits ``lavfi.r128.S`` metadata once per short-term frame.  Summary
    values are accepted as a fallback because they are present on supported
    FFmpeg versions even when metadata output is unavailable.
    """
    samples = [
        value
        for match in re.finditer(r"lavfi\.r128\.S\s*=\s*([-+]?\S+)", output, re.I)
        if (value := _number(match.group(1))) is not None
    ]
    summary = _summary(output)
    recognized_summary = re.search(r"(?:^|\n)\s*(?:I|LRA|Peak):\s*[-+]?inf", output, re.I)
    if (
        summary.integrated is None
        and summary.lra is None
        and summary.peak is None
        and not samples
        and recognized_summary is None
    ):
        raise EbuR128AnalysisError("parse", "FFmpeg output contained no EBU R128 measurements")
    return derive_mastering_measurements(summary.integrated, summary.lra, summary.peak, samples)


class EbuR128Analyzer:
    """Run one isolated FFmpeg pass and return pure numeric measurements."""

    def __init__(self, ffmpeg: str = "ffmpeg", *, max_output_bytes: int = 1_000_000) -> None:
        self._ffmpeg = ffmpeg
        self._max_output_bytes = max_output_bytes

    def analyze(self, path: Path, *, timeout: float) -> MasteringMeasurements:
        argv = [
            self._ffmpeg,
            "-nostdin",
            "-v",
            "info",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-filter:a",
            "ebur128=metadata=1:peak=true,ametadata=print:file=-",
            "-vn",
            "-f",
            "null",
            "-",
        ]
        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        environment["LANG"] = "C"
        try:
            result = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise EbuR128AnalysisError("timeout", "FFmpeg analysis timed out") from exc
        except OSError as exc:
            raise EbuR128AnalysisError("process", "FFmpeg could not be started") from exc
        output = f"{result.stdout}\n{result.stderr}"
        if result.returncode:
            diagnostic = output[-_MAX_DIAGNOSTICS:]
            raise EbuR128AnalysisError("process", "FFmpeg analysis failed: " + diagnostic)
        if len(output.encode()) > self._max_output_bytes:
            raise EbuR128AnalysisError("output", "FFmpeg diagnostics exceeded the configured bound")
        return parse_ebur128_output(output)
