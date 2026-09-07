"""Read-only curation projections for DJ Digger catalogs.

Exports are lazy so the model-client subprocess can load its bounded protocol
without importing the catalog or SQLite stack. The cache in ``__getattr__``
keeps every exported object identical to its canonical submodule object.
"""

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "CandidateDetailsV1": ("models", "CandidateDetailsV1"),
    "CandidateDetails": ("models", "CandidateDetails"),
    "CandidateRef": ("models", "CandidateRef"),
    "CandidateSearchV1": ("models", "CandidateSearchV1"),
    "CurationCatalog": ("catalog", "CurationCatalog"),
    "CurationCatalogError": ("catalog", "CurationCatalogError"),
    "LibraryOverviewV1": ("models", "LibraryOverviewV1"),
    "SearchFilters": ("models", "SearchFilters"),
    "CreateCurationDraft": ("models", "CreateCurationDraft"),
    "CurationCreation": ("models", "CurationCreation"),
    "CurationKind": ("models", "CurationKind"),
    "CurationRepository": ("repository", "CurationRepository"),
    "CurationStatus": ("models", "CurationStatus"),
    "CurationTrack": ("models", "CurationTrack"),
}

__all__ = [
    "CandidateDetailsV1",
    "CandidateDetails",
    "CandidateRef",
    "CandidateSearchV1",
    "CurationCatalog",
    "CurationCatalogError",
    "LibraryOverviewV1",
    "SearchFilters",
    "CreateCurationDraft",
    "CurationCreation",
    "CurationKind",
    "CurationRepository",
    "CurationStatus",
    "CurationTrack",
]


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError:
        raise AttributeError(name) from None
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
