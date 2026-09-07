"""Compatibility re-exports for :mod:`dj_digger.core.curation`."""

from dj_digger.core.curation import (
    CandidateDetails,
    CandidateDetailsV1,
    CandidateRef,
    CandidateSearchV1,
    CreateCurationDraft,
    CurationCatalog,
    CurationCatalogError,
    CurationCreation,
    CurationKind,
    CurationRepository,
    CurationStatus,
    CurationTrack,
    LibraryOverviewV1,
    SearchFilters,
)

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
