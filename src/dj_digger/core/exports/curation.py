"""Publish a persisted curation from one catalog snapshot.

Playlists without copied files use absolute paths and are intentionally only
supported for a single source (the retained consumer context). Multi-source playlists require
``copy_files=True`` so the exported playlist is portable and unambiguous.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dj_digger.core.catalog.database import Database
from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.set_copy import copy_track_atomic

CurationExportContent = Literal["playlist", "report", "both"]


@dataclass(frozen=True)
class CurationExportResult:
    """A completely published curation export."""

    output: Path
    artifacts: tuple[Path, ...]
    track_count: int


@dataclass(frozen=True)
class _Track:
    source_id: str
    track_id: int
    relative_path: str
    size_bytes: int
    mtime_ns: int


def export_curation(
    database: Database,
    config: WorkspaceConfig,
    creation_id: str,
    *,
    content: CurationExportContent,
    copy_files: bool,
    output: Path,
) -> CurationExportResult:
    """Stage and atomically publish one persisted draft or validated curation."""
    if content not in {"playlist", "report", "both"}:
        raise ValueError("--content must be playlist, report, or both")
    output = output.absolute()
    _validate_destination(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        with database.read_transaction():
            row = database.execute(
                "SELECT report_markdown FROM curation_creations WHERE id = ?", (creation_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown curation ID: {creation_id}")
            report = str(row[0])
            tracks = tuple(
                _Track(
                    str(source_id),
                    int(track_id),
                    str(relative_path),
                    int(size_bytes),
                    int(mtime_ns),
                )
                for source_id, track_id, relative_path, size_bytes, mtime_ns in database.execute(
                    """
                    SELECT t.source_id, t.id, t.relative_path, t.size_bytes, t.mtime_ns
                    FROM curation_creation_tracks AS ct
                    JOIN tracks AS t ON t.id = ct.track_id
                    WHERE ct.creation_id = ?
                    ORDER BY ct.position
                    """,
                    (creation_id,),
                )
            )
            if not tracks:
                raise ValueError("curation contains no tracks")
            roots = {source.id: source.path.resolve() for source in config.sources}
            selected_sources = {track.source_id for track in tracks}
            if content in {"playlist", "both"} and not copy_files and len(selected_sources) > 1:
                raise ValueError(
                    "multi-source playlists require --copy-files and a portable --output target"
                )
            for track in tracks:
                _validate_relative_track_path(track)
            needs_audio = copy_files or content in {"playlist", "both"}
            resolved = (
                tuple(_resolve_track(track, roots) for track in tracks) if needs_audio else ()
            )
            playlist_entries: list[str] = []
            if copy_files:
                track_dir = staging / "tracks"
                track_dir.mkdir()
                width = max(2, len(str(len(resolved))))
                for position, (track, source) in enumerate(zip(tracks, resolved, strict=True), 1):
                    name = f"{position:0{width}d} - {source.name}"
                    copy_track_atomic(
                        source,
                        track_dir,
                        name,
                        None,
                        expected_size=track.size_bytes,
                        expected_mtime_ns=track.mtime_ns,
                    )
                    _resolve_track(track, roots)
                    playlist_entries.append(_playlist_entry(f"tracks/{name}"))
            else:
                playlist_entries = [_playlist_entry(str(path)) for path in resolved]

            artifacts: list[Path] = []
            if content in {"playlist", "both"}:
                playlist = staging / "curation.m3u8"
                playlist.write_text(
                    "#EXTM3U\n" + "\n".join(playlist_entries) + "\n", encoding="utf-8"
                )
                artifacts.append(Path("curation.m3u8"))
            if content in {"report", "both"}:
                (staging / "report.md").write_bytes(report.encode("utf-8"))
                artifacts.append(Path("report.md"))
        _fsync_tree(staging)
        os.replace(staging, output)
        return CurationExportResult(
            output, tuple(output / artifact for artifact in artifacts), len(tracks)
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _validate_destination(output: Path) -> None:
    try:
        status = output.lstat()
    except FileNotFoundError:
        return
    kind = "symbolic link" if stat.S_ISLNK(status.st_mode) else "existing path"
    raise ValueError(f"refusing to overwrite destination {kind}: {output}")


def _resolve_track(track: _Track, roots: dict[str, Path]) -> Path:
    root = roots.get(track.source_id)
    if root is None:
        raise ValueError(f"source is not configured: {track.source_id}")
    relative = _validate_relative_track_path(track)
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        raise ValueError(
            f"track {track.source_id}/{track.track_id} is missing; rescan: {track.relative_path}"
        ) from None
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(
            f"track {track.source_id}/{track.track_id} escapes its configured source: "
            f"{track.relative_path}"
        )
    status = resolved.stat()
    if status.st_size != track.size_bytes or status.st_mtime_ns != track.mtime_ns:
        raise ValueError(
            f"track identity changed for {track.source_id}/{track.track_id}; rescan: "
            f"{track.relative_path}"
        )
    return resolved


def _validate_relative_track_path(track: _Track) -> Path:
    relative = Path(track.relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe relative track path for source {track.source_id}")
    return relative


def _playlist_entry(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("track path cannot be represented safely in M3U8")
    return value


def _fsync_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
