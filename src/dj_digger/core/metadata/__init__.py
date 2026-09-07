"""Canonical embedded audio metadata services."""

from dj_digger.core.metadata.exiftool import (
    EMBEDDED_FIELDS,
    EmbeddedMetadata,
    ExifToolExtractor,
    ExtractionBatch,
    ExtractionError,
    MetadataRunResult,
    MetadataService,
)

__all__ = [
    "EMBEDDED_FIELDS",
    "EmbeddedMetadata",
    "ExifToolExtractor",
    "ExtractionBatch",
    "ExtractionError",
    "MetadataRunResult",
    "MetadataService",
]
