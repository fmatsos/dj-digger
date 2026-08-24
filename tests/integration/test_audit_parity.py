"""Parity coverage for every category in the historical library audit."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from dj_digger.application import WorkspaceApplication
from dj_digger.config import ExportConfig, LibrarySourceConfig, WorkspaceConfig

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


def _old_inventory_rows(root: Path) -> list[dict[str, str]]:
    """Oracle for generate_inventory() in export-music-audit.sh."""
    rows: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        stat = path.stat()
        relative = path.relative_to(root).as_posix()
        rows.append(
            {
                "path": relative,
                "filename": path.name,
                "extension": path.suffix.lower(),
                "size_bytes": str(stat.st_size),
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return rows


def _old_directory_paths(root: Path) -> set[str]:
    """Oracle for generate_directories()'s find -type d -printf '%P' contract."""
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()}


def _old_directory_stats(rows: list[dict[str, str]]) -> list[tuple[int, str, int]]:
    """Oracle for the level-one and level-two counters in generate_inventory()."""
    level_one: Counter[str] = Counter()
    level_two: Counter[str] = Counter()
    for row in rows:
        parts = Path(row["path"]).parts[:-1]
        if parts:
            level_one[parts[0]] += 1
        if len(parts) >= 2:
            level_two["/".join(parts[:2])] += 1
    return sorted(
        [(1, path, count) for path, count in level_one.items()]
        + [(2, path, count) for path, count in level_two.items()],
        key=lambda item: (-item[2], item[1]),
    )


def _old_artifact_paths(root: Path) -> set[str]:
    """Oracle for generate_dj_metadata_inventory() in export-music-audit.sh.

    This intentionally mirrors its documented predicates rather than reusing
    the catalog classifier, so a shared bug cannot make this parity test pass.
    """
    paths: set[str] = set()
    extensions = {
        ".nml",
        ".tsi",
        ".m3u",
        ".m3u8",
        ".pls",
        ".cue",
        ".xml",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".crate",
        ".scrate",
        ".session",
    }
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        parts = {part.lower() for part in path.relative_to(root).parts}
        if (
            path.suffix.lower() in extensions
            or path.name.lower() in {"database", "database v2"}
            or "_serato_" in parts
        ):
            paths.add(relative)
    return paths


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _read_metadata_paths(path: Path) -> set[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["SourceFile"] for row in csv.DictReader(handle)}


def normalized_legacy_rows(rows: list[dict[str, str]]) -> list[tuple[str, str, str, str, str]]:
    """Freeze only historical inventory formatting: POSIX paths and second precision."""
    return sorted(
        (
            row["path"].replace("\\", "/"),
            row["filename"],
            row["extension"].lower(),
            str(row["size_bytes"]),
            datetime.fromisoformat(row["mtime"]).isoformat(timespec="seconds"),
        )
        for row in rows
    )


def test_catalog_audit_facets_match_historical_exporter_contract(tmp_path: Path) -> None:
    """Parity against the reference shell exporter without requiring ExifTool."""
    config = WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "audit",
        export=ExportConfig(True),
        sources=(
            LibrarySourceConfig("djing", tmp_path / "djing", True, True),
            LibrarySourceConfig("music", PARITY_LIBRARY, True, True),
        ),
    )
    (tmp_path / "djing").mkdir()
    application = WorkspaceApplication(config)
    assert all(result.succeeded for result in application.scan())

    output = config.exports
    application.export("artifacts")

    old_rows = _old_inventory_rows(PARITY_LIBRARY)
    new_rows = _read_tsv(output / "music-files.tsv")
    old_inventory_paths = {row["path"] for row in old_rows}
    new_inventory_paths = {row["path"] for row in new_rows}
    old_directory_paths = _old_directory_paths(PARITY_LIBRARY)
    new_directory_paths = set((output / "music-directories.txt").read_text().splitlines())
    old_artifact_paths = _old_artifact_paths(PARITY_LIBRARY)
    new_artifact_paths = {row["path"] for row in _read_tsv(output / "dj-metadata-files.tsv")}

    assert new_inventory_paths == old_inventory_paths
    assert new_directory_paths == old_directory_paths
    assert new_artifact_paths == old_artifact_paths
    assert normalized_legacy_rows(new_rows) == normalized_legacy_rows(old_rows)
    new_metadata_paths = _read_metadata_paths(output / "music-metadata.csv")
    assert new_metadata_paths == old_inventory_paths
    assert len(_read_tsv(output / "music-files.tsv")) == len(new_metadata_paths)
    assert _old_directory_stats(old_rows) == [
        (int(row["level"]), row["path"], int(row["tracks"]))
        for row in _read_tsv(output / "music-directory-stats.tsv")
    ]
