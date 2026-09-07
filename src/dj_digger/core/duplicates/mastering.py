"""Pure, finite-safe mastering and DJ usability calculations."""

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite

MASTERING_ANALYSIS_VERSION = "ffmpeg-ebur128/1"


@dataclass(frozen=True)
class MasteringMeasurements:
    integrated_lufs: float | None
    loudness_range_lu: float | None
    true_peak_dbtp: float | None
    short_term_lufs_p50: float | None
    short_term_lufs_p95: float | None
    peak_to_loudness_ratio_db: float | None


@dataclass(frozen=True)
class DjMetrics:
    required_gain_db: float | None
    available_gain_db: float | None
    gain_deficit_db: float | None


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        return None
    return float(value)


def percentiles(values: Iterable[object]) -> tuple[float | None, float | None]:
    """Return linearly interpolated P50 and P95 of finite values."""
    ordered = sorted(value for raw in values if (value := _finite(raw)) is not None)
    if not ordered:
        return None, None

    def percentile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        weight = position - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * weight

    return percentile(0.50), percentile(0.95)


def derive_mastering_measurements(
    integrated_lufs: object,
    loudness_range_lu: object,
    true_peak_dbtp: object,
    short_term_lufs: Iterable[object] | None = None,
) -> MasteringMeasurements:
    integrated = _finite(integrated_lufs)
    loudness_range = _finite(loudness_range_lu)
    true_peak = _finite(true_peak_dbtp)
    p50, p95 = percentiles(short_term_lufs or ())
    plr = None if integrated is None or true_peak is None else _finite(true_peak - integrated)
    return MasteringMeasurements(integrated, loudness_range, true_peak, p50, p95, plr)


def derive_dj_metrics(
    integrated_lufs: object,
    true_peak_dbtp: object,
    *,
    target_lufs: object,
    target_peak_dbtp: object,
) -> DjMetrics:
    integrated = _finite(integrated_lufs)
    true_peak = _finite(true_peak_dbtp)
    target_loudness = _finite(target_lufs)
    target_peak = _finite(target_peak_dbtp)
    required = (
        None
        if integrated is None or target_loudness is None
        else _finite(target_loudness - integrated)
    )
    available = (
        None if true_peak is None or target_peak is None else _finite(target_peak - true_peak)
    )
    deficit = (
        None if required is None or available is None else _finite(max(0.0, required - available))
    )
    return DjMetrics(required, available, deficit)
