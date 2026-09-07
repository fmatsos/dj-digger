"""Compatibility exports for the portable set-copy API."""

from dj_digger.core.application.copy_set import CopySetRequest, CopySetUseCase, copy_set
from dj_digger.core.set_copy import (
    SetCopyResult,
    _copy_track_atomic,
    _resolve_owner,
    _set_recursive_ownership,
    copy_track_atomic,
)

__all__ = [
    "CopySetRequest",
    "CopySetUseCase",
    "SetCopyResult",
    "_copy_track_atomic",
    "_resolve_owner",
    "_set_recursive_ownership",
    "copy_set",
    "copy_track_atomic",
]
