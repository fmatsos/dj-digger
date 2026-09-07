"""Compatibility imports for catalog migrations."""

from importlib.resources import files

from dj_digger.core.catalog.migrations import (
    CURRENT_SCHEMA,
    CURRENT_VERSION,
    MIGRATIONS,
    _load_sql,
    _version,
    initialize_catalog,
    migrate,
    upgrade_catalog_20260827105404,
    upgrade_catalog_20260827225144,
    upgrade_catalog_20260828150213,
    upgrade_catalog_20260905221652,
    upgrade_catalog_20260907063758,
)

__all__ = [
    "CURRENT_SCHEMA",
    "CURRENT_VERSION",
    "MIGRATIONS",
    "_load_sql",
    "_version",
    "files",
    "initialize_catalog",
    "migrate",
    "upgrade_catalog_20260827105404",
    "upgrade_catalog_20260827225144",
    "upgrade_catalog_20260828150213",
    "upgrade_catalog_20260905221652",
    "upgrade_catalog_20260907063758",
]
