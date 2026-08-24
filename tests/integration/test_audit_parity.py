"""Parity coverage for every category in the historical library audit."""
from __future__ import annotations

from pathlib import Path

PARITY_LIBRARY = Path(__file__).resolve().parents[1] / "fixtures" / "parity-library"
EXPECTED = {
    "audio",
    "empty_directory",
    "traktor",
    "serato",
    "playlist",
    "cue",
    "xml",
    "database",
}

AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac", ".ogg", ".opus"}
PLAYLIST_EXTENSIONS = {".m3u", ".m3u8", ".pls"}
DATABASE_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}


def fixture_categories(root: Path) -> set[str]:
    """Return the historical audit categories represented below ``root``."""
    assert root.is_dir(), f"missing parity fixture: {root}"
    categories: set[str] = set()
    for path in sorted(root.rglob("*")):
        relative_parts = tuple(part.lower() for part in path.relative_to(root).parts)
        if path.is_dir():
            if not any(child.name != ".gitkeep" for child in path.iterdir()):
                categories.add("empty_directory")
            continue

        suffix = path.suffix.lower()
        if suffix in AUDIO_EXTENSIONS:
            categories.add("audio")
        if suffix in {".nml", ".tsi"}:
            categories.add("traktor")
        if "_serato_" in relative_parts:
            categories.add("serato")
        if suffix in PLAYLIST_EXTENSIONS:
            categories.add("playlist")
        if suffix == ".cue":
            categories.add("cue")
        if suffix == ".xml":
            categories.add("xml")
        if suffix in DATABASE_EXTENSIONS or path.name.lower() in {"database", "database v2"}:
            categories.add("database")
    return categories


def test_parity_library_covers_every_historical_audit_category() -> None:
    assert fixture_categories(PARITY_LIBRARY) == EXPECTED
