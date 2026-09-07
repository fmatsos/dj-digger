"""Compatibility re-exports for canonical duplicate persistence."""

from dj_digger.core.duplicates.repository import (
    DuplicateGroup,
    DuplicateGroupMember,
    DuplicateRepository,
)

__all__ = ["DuplicateGroup", "DuplicateGroupMember", "DuplicateRepository"]
