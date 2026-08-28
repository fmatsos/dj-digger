"""Read-only FFmpeg technical audio probing."""

import dataclasses
import json
import re
import subprocess
from pathlib import Path

from dj_digger.analysis.audio import TechnicalAudioMetadata

_LOSSLESS_CODECS = {"alac", "ape", "flac", "pcm_s16le", "pcm_s24le", "pcm_s32le", "wavpack"}


class FFmpegProbe:
    """Probe one audio file with ffprobe and non-writing FFmpeg filters."""

    def __init__(self, ffprobe: str = "ffprobe", ffmpeg: str = "ffmpeg") -> None:
        self._ffprobe = ffprobe
        self._ffmpeg = ffmpeg

    def probe(self, path: Path) -> TechnicalAudioMetadata:
        """Return technical facts plus loudness measurements from a full ebur128 pass."""
        facts = self.probe_facts(path)
        loudness_lufs, true_peak_db, dynamic_range = self._measure(path)
        return dataclasses.replace(
            facts,
            loudness_lufs=loudness_lufs,
            true_peak_db=true_peak_db,
            dynamic_range=dynamic_range,
        )

    def probe_facts(self, path: Path) -> TechnicalAudioMetadata:
        """Return lightweight FFprobe facts without running the loudness measurement."""
        facts = self._facts(path)
        return TechnicalAudioMetadata(
            duration_seconds=_number(facts.get("duration")),
            sample_rate=_integer(facts.get("sample_rate")),
            channels=_integer(facts.get("channels")),
            codec=_text(facts.get("codec_name")),
            container=_container(facts.get("format_name")),
            bitrate=_integer(facts.get("bit_rate")),
            lossless=_lossless(facts.get("codec_name")),
            bit_depth=_integer(facts.get("bits_per_raw_sample"))
            or _integer(facts.get("bits_per_sample")),
        )

    def _facts(self, path: Path) -> dict[str, object]:
        result = subprocess.run(
            [
                self._ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            payload = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        stream = next(
            (
                item for item in payload.get("streams", [])
                if isinstance(item, dict) and item.get("codec_type") == "audio"
            ),
            {},
        )
        format_data = payload.get("format")
        if not isinstance(format_data, dict):
            format_data = {}
        if not isinstance(stream, dict):
            stream = {}
        return {**format_data, **stream}

    def _measure(self, path: Path) -> tuple[float | None, float | None, float | None]:
        result = subprocess.run(
            [
                self._ffmpeg,
                "-v",
                "info",
                "-i",
                str(path),
                "-filter:a",
                "ebur128=peak=true",
                "-f",
                "null",
                "-",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        output = f"{result.stdout}\n{result.stderr}"
        return (
            _measurement(output, "I"),
            _measurement(output, "Peak"),
            _measurement(output, "LRA") or _measurement(output, "Dynamic range"),
        )


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _container(value: object) -> str | None:
    text = _text(value)
    return text.split(",", 1)[0] if text else None


def _number(value: object) -> float | None:
    try:
        return float(value) if isinstance(value, (int, float, str)) else None
    except (TypeError, ValueError):
        return None


def _integer(value: object) -> int | None:
    try:
        return int(value) if isinstance(value, (int, str)) else None
    except (TypeError, ValueError):
        return None


def _lossless(value: object) -> bool | None:
    codec = _text(value)
    if codec is None:
        return None
    return codec.lower() in _LOSSLESS_CODECS


def _measurement(output: str, label: str) -> float | None:
    match = re.search(rf"(?:^|\n)\s*{re.escape(label)}:\s*(-?\d+(?:\.\d+)?)", output)
    return _number(match.group(1)) if match else None
