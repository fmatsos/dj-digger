"""Classify DJ metadata artifacts encountered during a library traversal."""

from pathlib import Path


def classify_dj_artifact(relative_path: Path) -> str | None:
    """Return the supported artifact type for a source-relative path, if any."""
    parts = tuple(part.lower() for part in relative_path.parts)
    suffix = relative_path.suffix.lower()
    if "_serato_" in parts:
        return {
            ".crate": "serato_crate",
            ".scrate": "serato_smart_crate",
            ".session": "serato_session",
        }.get(suffix, "serato_internal")

    by_suffix = {
        ".nml": "traktor_nml",
        ".tsi": "traktor_tsi",
        ".m3u": "playlist_m3u",
        ".m3u8": "playlist_m3u8",
        ".pls": "playlist_pls",
        ".cue": "cue",
        ".xml": "xml",
        ".db": "database",
        ".sqlite": "database",
        ".sqlite3": "database",
    }
    if suffix in by_suffix:
        return by_suffix[suffix]
    if relative_path.name.lower() in {"database", "database v2"}:
        return "database"
    return None
