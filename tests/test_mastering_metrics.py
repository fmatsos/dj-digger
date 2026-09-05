import pytest

from dj_digger.duplicates.mastering import (
    DjMetrics,
    MasteringMeasurements,
    derive_dj_metrics,
    derive_mastering_measurements,
    percentiles,
)


def test_gain_without_deficit() -> None:
    result = derive_dj_metrics(-13.0, -5.0, target_lufs=-9.0, target_peak_dbtp=-1.0)

    assert result == DjMetrics(4.0, 4.0, 0.0)


def test_gain_with_peak_limited_deficit() -> None:
    result = derive_dj_metrics(-13.0, -0.2, target_lufs=-9.0, target_peak_dbtp=-1.0)

    assert result.required_gain_db == pytest.approx(4.0)
    assert result.available_gain_db == pytest.approx(-0.8)
    assert result.gain_deficit_db == pytest.approx(4.8)


def test_missing_or_non_finite_values_propagate_to_null() -> None:
    assert derive_dj_metrics(None, -1.0, target_lufs=-9.0, target_peak_dbtp=-1.0) == DjMetrics(
        None, 0.0, None
    )
    assert percentiles([float("nan"), float("inf")]) == (None, None)
    measurements = derive_mastering_measurements(float("nan"), float("inf"), 1.0, [0.0])
    assert measurements.integrated_lufs is None
    assert measurements.loudness_range_lu is None
    assert (
        derive_dj_metrics(
            float("nan"), 0.0, target_lufs=-9.0, target_peak_dbtp=-1.0
        ).required_gain_db
        is None
    )
    assert (
        derive_dj_metrics(
            -9.0, float("inf"), target_lufs=-9.0, target_peak_dbtp=-1.0
        ).available_gain_db
        is None
    )
    assert (
        derive_dj_metrics(
            -9.0, 0.0, target_lufs=float("nan"), target_peak_dbtp=-1.0
        ).required_gain_db
        is None
    )
    overflow = derive_mastering_measurements(-1.0, 1.0, -1.0e308, [1.0e308])
    assert overflow.peak_to_loudness_ratio_db == pytest.approx(-1.0e308)
    metrics = derive_dj_metrics(
        -1.0e308,
        1.0e308,
        target_lufs=1.0e308,
        target_peak_dbtp=-1.0e308,
    )
    assert metrics.required_gain_db is None
    assert metrics.available_gain_db is None
    assert metrics.gain_deficit_db is None


def test_mastering_measurements_filter_non_finite_samples() -> None:
    result = derive_mastering_measurements(
        -10.0,
        4.2,
        -0.4,
        [-12.0, -10.0, float("nan"), -8.0, float("inf")],
    )

    assert result == MasteringMeasurements(-10.0, 4.2, -0.4, -10.0, -8.2, 9.6)


def test_measurements_keep_usable_values_when_metrics_are_missing() -> None:
    result = derive_mastering_measurements(None, 4.2, -0.4, None)

    assert result.integrated_lufs is None
    assert result.loudness_range_lu == 4.2
    assert result.true_peak_dbtp == -0.4
    assert result.short_term_lufs_p50 is None
    assert result.short_term_lufs_p95 is None
    assert result.peak_to_loudness_ratio_db is None
