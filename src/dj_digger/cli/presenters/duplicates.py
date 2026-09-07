"""JSON view models for duplicate workflows."""

from collections.abc import Sequence
from typing import Any

from dj_digger.core.duplicates.quality import QualityMarkResult
from dj_digger.core.duplicates.service import (
    DuplicateAnalysisResult,
    DuplicateGroupDescription,
)


def duplicate_analysis_payload(result: DuplicateAnalysisResult) -> dict[str, Any]:
    """Map a typed analysis result to the historical compact JSON payload."""
    return {
        "event": "duplicates",
        "status": result.status,
        **result.__dict__,
    }


def duplicate_groups_payload(
    groups: Sequence[DuplicateGroupDescription], *, dj_review: bool = False
) -> dict[str, Any]:
    """Shape groups for JSON, applying review filtering and ordering only here."""
    selected = list(groups)
    if dj_review:
        selected = [group for group in selected if group.dj_review_recommended is True]
        selected.sort(key=_review_sort_key)
    return {
        "event": "duplicates",
        "status": "succeeded",
        "groups": [_group_json(group) for group in selected],
    }


def duplicate_mark_best_payload(result: QualityMarkResult) -> dict[str, Any]:
    """Map a typed quality-selection result to the historical JSON payload."""
    return {
        "event": "duplicates",
        "status": result.status,
        "marked_best": result.marked_best,
        "incomplete_track_ids": list(result.incomplete_track_ids),
    }


def _group_json(group: DuplicateGroupDescription) -> dict[str, Any]:
    return {
        "group_id": group.group_id,
        "mastering_variant": group.mastering_variant,
        "dj_review_recommended": group.dj_review_recommended,
        "analysis_complete": group.analysis_complete,
        "comparison_status": group.comparison_status,
        "members": [
            {
                "source": member.source_id,
                "track_id": member.track_id,
                "relative_path": member.relative_path,
                "technical_facts": member.technical_facts,
                "best_quality": member.best_quality,
                "audio_analysis": member.audio_analysis,
                "dj_analysis": member.dj_analysis,
                "mastering_comparison": (
                    None
                    if member.mastering_comparison is None
                    else member.mastering_comparison.__dict__
                ),
            }
            for member in group.members
        ],
    }


def _review_sort_key(group: DuplicateGroupDescription) -> tuple[int, float, float, str]:
    deficits: list[float] = []
    for member in group.members:
        if member.dj_analysis is None:
            continue
        value = member.dj_analysis.get("gain_deficit_db")
        if isinstance(value, (int, float)):
            deficits.append(float(value))
    deltas: list[float] = []
    for member in group.members:
        comparison = member.mastering_comparison
        if comparison is None:
            continue
        for name in (
            "active_loudness_delta_db",
            "true_peak_delta_db",
            "plr_delta_db",
            "gain_deficit_delta_db",
        ):
            value = getattr(comparison, name)
            if value is not None:
                deltas.append(abs(value))
    return (
        0 if deficits else 1,
        -(max(deficits) if deficits else 0.0),
        -(max(deltas) if deltas else 0.0),
        group.group_id,
    )


__all__ = [
    "_group_json",
    "_review_sort_key",
    "duplicate_analysis_payload",
    "duplicate_groups_payload",
    "duplicate_mark_best_payload",
]
