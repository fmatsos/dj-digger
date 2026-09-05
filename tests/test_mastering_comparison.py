from dj_digger.config import ComparisonThresholds, MasteringConfig
from dj_digger.duplicates.mastering_comparison import compare_group


def test_review_thresholds_are_independent_from_variant_thresholds() -> None:
    config = MasteringConfig(
        variant_thresholds=ComparisonThresholds(
            active_loudness_db=10.0,
            true_peak_db=10.0,
            plr_db=10.0,
            integrated_lufs_db=10.0,
            lra_lu=10.0,
        ),
        review_thresholds=ComparisonThresholds(
            active_loudness_db=10.0,
            true_peak_db=10.0,
            plr_db=10.0,
            integrated_lufs_db=None,
            lra_lu=None,
            gain_deficit_db=1.5,
        ),
    )
    members = [
        {
            "track_id": 1,
            "gain_deficit_db": 0.0,
            "_mastering_present": True,
            "_dj_present": True,
        },
        {
            "track_id": 2,
            "gain_deficit_db": 2.0,
            "_mastering_present": True,
            "_dj_present": True,
        },
    ]

    result = compare_group(members, 1, config)

    assert result.mastering_variant is False
    assert result.dj_review_recommended is True
    assert result.members[2].gain_deficit_delta_db == 2.0
