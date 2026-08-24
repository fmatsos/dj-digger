"""Filesystem entry classification used by source scanning."""

from enum import StrEnum
from pathlib import Path

from dj_digger.artifacts.discovery import classify_dj_artifact

AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac", ".ogg", ".opus"}


class EntryKind(StrEnum):
    """Kinds of entries which matter to a source observation."""

    DIRECTORY = "directory"
    AUDIO = "audio"
    ARTIFACT = "artifact"
    OTHER = "other"


def classify(relative_path: Path, *, is_dir: bool) -> EntryKind:
    """Classify an entry without changing its original filesystem spelling."""
    if is_dir:
        return EntryKind.DIRECTORY
    if relative_path.suffix.lower() in AUDIO_EXTENSIONS:
        return EntryKind.AUDIO
    if classify_dj_artifact(relative_path) is not None:
        return EntryKind.ARTIFACT
    return EntryKind.OTHER
