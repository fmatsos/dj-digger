"""Single-track audio analysis worker using a versioned JSON protocol."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from dj_digger.analysis.extractor import (
    AnalysisExtractionError,
    AnalysisExtractionResult,
    CompositeAudioExtractor,
)
from dj_digger.config import DspConfig

PROTOCOL_VERSION = 1
MAX_ERROR_LENGTH = 4_000
ExtractorFactory = Callable[[DspConfig], Any]


def execute_request(
    request: Mapping[str, object],
    *,
    extractor_factory: ExtractorFactory = CompositeAudioExtractor,
) -> dict[str, object]:
    """Validate and execute one request without accessing the catalog database."""
    try:
        path, source_id, track_id, relative_path, dsp = _parse_request(request)
        extraction: AnalysisExtractionResult = extractor_factory(dsp).extract(
            path,
            source_id=source_id,
            track_id=track_id,
            relative_path=relative_path,
        )
        if extraction.status != "succeeded":
            raise AnalysisExtractionError(
                "aggregation",
                f"worker extraction returned non-success status: {extraction.status}",
            )
        return {
            "protocol_version": PROTOCOL_VERSION,
            "status": "succeeded",
            "result": {
                "payload": extraction.payload,
                "sections": extraction.sections,
                "confidence": extraction.confidence,
                "status": extraction.status,
            },
        }
    except AnalysisExtractionError as error:
        return _failure(error.stage, str(error))
    except Exception as error:
        return _failure("aggregation", str(error))


def _failure(stage: str, message: str) -> dict[str, object]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "status": "failed",
        "error": {"stage": stage, "message": message[:MAX_ERROR_LENGTH]},
    }


def _parse_request(
    request: Mapping[str, object],
) -> tuple[Path, str, int, str, DspConfig]:
    if request.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("unsupported worker protocol version")
    path = request.get("path")
    track = request.get("track")
    dsp = request.get("dsp")
    if not isinstance(path, str) or not isinstance(track, Mapping) or not isinstance(dsp, Mapping):
        raise ValueError("worker request requires path, track and dsp objects")
    source_id = track.get("source_id")
    track_id = track.get("track_id")
    relative_path = track.get("relative_path")
    if (
        not isinstance(source_id, str)
        or not isinstance(track_id, int)
        or isinstance(track_id, bool)
        or not isinstance(relative_path, str)
    ):
        raise ValueError("worker track identity is invalid")
    return Path(path), source_id, track_id, relative_path, _parse_dsp(dsp)


def _parse_dsp(raw: Mapping[str, object]) -> DspConfig:
    bands = raw.get("bands")
    if not isinstance(bands, Mapping):
        raise ValueError("worker DSP bands are invalid")
    parsed_bands: dict[str, tuple[float, float]] = {}
    for name, limits in bands.items():
        if not isinstance(name, str) or not isinstance(limits, list) or len(limits) != 2:
            raise ValueError("worker DSP band is invalid")
        lower, upper = limits
        if not _is_number(lower) or not _is_number(upper):
            raise ValueError("worker DSP band limits are invalid")
        parsed_bands[name] = (float(lower), float(upper))
    try:
        return DspConfig(
            version=_integer(raw["version"]),
            sample_rate=_integer(raw["sample_rate"]),
            channels=_integer(raw["channels"]),
            fft_window_size=_integer(raw["fft_window_size"]),
            fft_hop_size=_integer(raw["fft_hop_size"]),
            bands=parsed_bands,
            segmentation_min_seconds=_number(raw["segmentation_min_seconds"]),
            segmentation_max_seconds=_number(raw["segmentation_max_seconds"]),
            semantic_min_confidence=_number(raw["semantic_min_confidence"]),
        )
    except KeyError as error:
        raise ValueError(f"worker DSP field is missing: {error.args[0]}") from None


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("worker DSP integer is invalid")
    return value


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number(value: object) -> float:
    if not _is_number(value):
        raise ValueError("worker DSP number is invalid")
    return float(cast(int | float, value))


def main() -> int:
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, Mapping):
            raise ValueError("worker request must be a JSON object")
        response = execute_request(raw)
    except Exception as error:
        response = _failure("aggregation", str(error))
    json.dump(response, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
