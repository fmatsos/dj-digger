"""Lazy compatibility aliases for the canonical core analysis package."""

from importlib import import_module
from types import ModuleType

_MODULES = frozenset(
    {
        "aggregation",
        "audio",
        "config",
        "ebur128",
        "eligibility",
        "exporters",
        "extractor",
        "ffmpeg",
        "persistence",
        "pipeline",
        "rhythm",
        "segmentation",
        "semantics",
        "spectrum",
        "windows",
        "worker_client",
    }
)


def __getattr__(name: str) -> ModuleType:
    """Resolve legacy module attributes only when a caller requests them."""
    if name not in _MODULES:
        raise AttributeError(name)
    return import_module(f"dj_digger.core.analysis.{name}")


__all__ = [
    *_MODULES,
]
