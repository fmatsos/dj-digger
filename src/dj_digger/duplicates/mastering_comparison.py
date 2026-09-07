"""Compatibility re-exports for canonical mastering comparisons."""

from dj_digger.core.duplicates.mastering_comparison import (
    GroupMasteringComparison,
    MasteringComparison,
    compare_group,
    compare_member,
)

__all__ = ["GroupMasteringComparison", "MasteringComparison", "compare_group", "compare_member"]
