"""Value objects produced by technical audio probes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TechnicalAudioMetadata:
    """Normalized technical facts and optional read-only measurements."""

    duration_seconds: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    codec: str | None = None
    container: str | None = None
    bitrate: int | None = None
    lossless: bool | None = None
    loudness_lufs: float | None = None
    true_peak_db: float | None = None
    dynamic_range: float | None = None
