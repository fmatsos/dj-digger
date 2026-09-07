"""Compatibility imports for catalog repositories."""

from dj_digger.core.catalog.repositories import (
    ArtifactRepository,
    DirectoryRepository,
    EmbeddedMetadataRepository,
    EventRepository,
    ScanRunRepository,
    SourceRepository,
    TechnicalAudioMetadataRepository,
    TrackObservation,
    TrackRepository,
    _now,
)

__all__ = [
    "ArtifactRepository",
    "DirectoryRepository",
    "EmbeddedMetadataRepository",
    "EventRepository",
    "ScanRunRepository",
    "SourceRepository",
    "TechnicalAudioMetadataRepository",
    "TrackObservation",
    "TrackRepository",
    "_now",
]
