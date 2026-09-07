"""Compatibility re-exports for the canonical curation catalog."""

from dj_digger.core.curation.catalog import CurationCatalog, CurationCatalogError

__all__ = ["CurationCatalogError", "CurationCatalog"]
