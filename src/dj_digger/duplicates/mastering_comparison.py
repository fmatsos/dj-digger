"""Pure comparison of duplicate members' mastering observations."""

from dataclasses import dataclass
from typing import Any

from dj_digger.config import ComparisonThresholds, MasteringConfig


@dataclass(frozen=True)
class MasteringComparison:
    loudness_delta_db: float | None = None
    active_loudness_delta_db: float | None = None
    true_peak_delta_db: float | None = None
    plr_delta_db: float | None = None
    lra_delta_lu: float | None = None
    gain_deficit_delta_db: float | None = None
    mastering_variant: bool | None = None
    dj_review_recommended: bool | None = None


@dataclass(frozen=True)
class GroupMasteringComparison:
    comparison_status: str
    analysis_complete: bool
    mastering_variant: bool | None
    dj_review_recommended: bool | None
    members: dict[int, MasteringComparison]


def _value(obj: Any, name: str) -> float | None:
    value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return value if isinstance(value, (int, float)) else None


def compare_member(
    member: Any = None,
    baseline: Any = None,
    thresholds: ComparisonThresholds | None = None,
    review_thresholds: ComparisonThresholds | None = None,
    **values: Any,
) -> MasteringComparison:
    """Compare one row against a baseline, retaining signed nullable deltas."""
    if "member_lufs" in values:
        member = {"integrated_lufs": values["member_lufs"]}
        baseline = {"integrated_lufs": values.get("baseline_lufs")}
        threshold = values.get("threshold")
        thresholds = ComparisonThresholds(integrated_lufs_db=threshold)
    thresholds = thresholds or ComparisonThresholds()
    review_thresholds = review_thresholds or thresholds
    if member is None:
        member = values
    names = {
        "loudness_delta_db": "integrated_lufs",
        "active_loudness_delta_db": "short_term_lufs_p95",
        "true_peak_delta_db": "true_peak_dbtp",
        "plr_delta_db": "peak_to_loudness_ratio_db",
        "lra_delta_lu": "loudness_range_lu",
        "gain_deficit_delta_db": "gain_deficit_db",
    }
    deltas: dict[str, float | None] = {}
    for output, source in names.items():
        member_value = _value(member, source)
        baseline_value = _value(baseline, source)
        deltas[output] = (
            None
            if member_value is None or baseline_value is None
            else member_value - baseline_value
        )
    variant_checks = (
        (deltas["loudness_delta_db"], thresholds.integrated_lufs_db),
        (deltas["active_loudness_delta_db"], thresholds.active_loudness_db),
        (deltas["true_peak_delta_db"], thresholds.true_peak_db),
        (deltas["plr_delta_db"], thresholds.plr_db),
        (deltas["lra_delta_lu"], thresholds.lra_lu),
    )
    review_checks = (
        (deltas["active_loudness_delta_db"], review_thresholds.active_loudness_db),
        (deltas["true_peak_delta_db"], review_thresholds.true_peak_db),
        (deltas["plr_delta_db"], review_thresholds.plr_db),
        (deltas["gain_deficit_delta_db"], review_thresholds.gain_deficit_db),
    )
    variant = any(
        delta is not None and threshold is not None and abs(delta) >= threshold
        for delta, threshold in variant_checks
    )
    review = any(
        delta is not None and threshold is not None and abs(delta) >= threshold
        for delta, threshold in review_checks
    )
    return MasteringComparison(**deltas, mastering_variant=variant, dj_review_recommended=review)


def compare_group(
    members: Any, preferred_track_id: int | None, config: MasteringConfig
) -> GroupMasteringComparison:
    """Compare all members to the explicitly marked technical winner."""
    if preferred_track_id is None:
        return GroupMasteringComparison("missing_best_quality", False, None, None, {})
    by_id = {int(_value(member, "track_id") or 0): member for member in members}
    baseline = by_id.get(preferred_track_id)
    if baseline is None:
        return GroupMasteringComparison("missing_best_quality", False, None, None, {})
    comparisons = {
        track_id: compare_member(
            member, baseline, config.variant_thresholds, config.review_thresholds
        )
        for track_id, member in by_id.items()
    }

    def present(member: Any, name: str) -> bool:
        if isinstance(member, dict):
            if name in member:
                return bool(member[name])
            return bool(
                member.get("audio_analysis" if name == "_mastering_present" else "dj_analysis")
            )
        return getattr(member, name, False) is not None

    complete = all(
        present(member, "_mastering_present") and present(member, "_dj_present")
        for member in by_id.values()
    )
    # A comparison can still be emitted for partial rows; flags remain conservative.
    if not complete:
        return GroupMasteringComparison("incomplete", False, None, None, comparisons)
    return GroupMasteringComparison(
        "complete",
        True,
        any(item.mastering_variant for item in comparisons.values()),
        any(item.dj_review_recommended for item in comparisons.values()),
        comparisons,
    )
