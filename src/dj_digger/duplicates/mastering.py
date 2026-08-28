"""Pure mastering measurements and DJ-readiness calculations."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

MASTERING_ANALYSIS_VERSION = "ffmpeg-ebur128/1"


def _finite(value: float | None) -> float | None:
    return value if value is not None and isfinite(value) else None


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


def percentiles(values: Sequence[float], *quantiles: float) -> tuple[float | None, ...]:
    clean = sorted(value for value in values if isfinite(value))
    if not clean:
        return tuple(None for _ in (quantiles or (0.5, 0.95)))
    result = []
    for quantile in quantiles or (0.5, 0.95):
        position = (len(clean) - 1) * quantile
        lower = int(position)
        upper = min(lower + 1, len(clean) - 1)
        result.append(clean[lower] + (clean[upper] - clean[lower]) * (position - lower))
    return tuple(result)


def derive_mastering_measurements(
    integrated_lufs: float | None,
    loudness_range_lu: float | None,
    true_peak_dbtp: float | None,
    short_term_lufs: Sequence[float],
) -> MasteringMeasurements:
    integrated_lufs = _finite(integrated_lufs)
    loudness_range_lu = _finite(loudness_range_lu)
    true_peak_dbtp = _finite(true_peak_dbtp)
    p50, p95 = percentiles(short_term_lufs)
    # PLR is a global peak-to-integrated-loudness observation.  Avoid using a
    # short-term percentile here: that is a separate active-loudness signal.
    plr = (
        None
        if true_peak_dbtp is None or integrated_lufs is None
        else _finite(true_peak_dbtp - integrated_lufs)
    )
    return MasteringMeasurements(integrated_lufs, loudness_range_lu, true_peak_dbtp, p50, p95, plr)


def derive_dj_metrics(
    integrated_lufs: float | None,
    true_peak_dbtp: float | None,
    *,
    target_lufs: float,
    target_peak_dbtp: float,
) -> DjMetrics:
    integrated_lufs = _finite(integrated_lufs)
    true_peak_dbtp = _finite(true_peak_dbtp)
    normalized_target_lufs = _finite(target_lufs)
    normalized_target_peak = _finite(target_peak_dbtp)
    required = (
        None
        if integrated_lufs is None or normalized_target_lufs is None
        else _finite(normalized_target_lufs - integrated_lufs)
    )
    available = (
        None
        if true_peak_dbtp is None or normalized_target_peak is None
        else _finite(normalized_target_peak - true_peak_dbtp)
    )
    deficit = (
        None if required is None or available is None else _finite(max(0.0, required - available))
    )
    return DjMetrics(required, available, deficit)
