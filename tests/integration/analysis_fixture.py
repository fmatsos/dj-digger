"""Deterministic, schema-complete analysis extraction fixtures."""

from dj_digger.analysis.extractor import AnalysisExtractionResult
from dj_digger.catalog.models import Track


def analysis_fixture(track: Track) -> AnalysisExtractionResult:
    """Return a valid dj-analysis row without invoking ffmpeg or audio DSP."""
    payload: dict[str, object] = {
        "source_id": track.source_id,
        "track_id": track.id,
        "path": track.relative_path,
        "size_bytes": track.size_bytes,
        "mtime": track.mtime_ns,
        "analysis_schema_version": 2,
        "analyzer_version": "dj-digger-analysis/2",
        "config_hash": "a" * 64,
        "analysis_status": "ok",
        "analysis_confidence": 0.75,
        "duration_seconds": 120.0,
        "sample_rate": 48000,
        "channels": 2,
        "codec": "flac",
        "container": "flac",
        "lossless": True,
        "bpm": 128.0,
        "bpm_confidence": 0.9,
        "beat_stability": 0.9,
        "key": "Am",
        "key_confidence": 0.8,
        "loudness_lufs": -10.0,
        "true_peak_db": -1.0,
        "dynamic_range": 8.0,
        "sub_energy": 0.2,
        "low_energy": 0.3,
        "low_mid_energy": 0.4,
        "kick_strength": 0.5,
        "kick_density": 0.5,
        "bass_density": 0.4,
        "onset_density": 0.3,
        "spectral_centroid": 1800.0,
    }
    for side in ("intro", "outro"):
        for bars in (8, 16, 32, 64):
            prefix = f"{side}_{bars}_"
            payload[prefix + "available"] = False
            for name in (
                "bpm",
                "beat_stability",
                "sub_energy",
                "low_energy",
                "low_mid_energy",
                "kick_strength",
                "kick_density",
                "bass_density",
                "loudness_lufs",
                "onset_density",
                "spectral_centroid",
            ):
                payload[prefix + name] = None
    return AnalysisExtractionResult(
        payload=payload,
        sections={
            "source_id": track.source_id,
            "track_id": track.id,
            "path": track.relative_path,
            "analysis_schema_version": 2,
            "sections": [],
        },
        confidence=0.75,
        status="succeeded",
    )
