"""Portable set-copy use case independent of the workspace catalog."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dj_digger.core.application.progress import ProgressEvent, ProgressSink
from dj_digger.core.set_copy import (
    OwnerResolver,
    OwnershipSetter,
    SetCopyResult,
    _copy_track_atomic,
    _open_target_directory,
    _publish_text,
    _resolve_owner,
    _resolve_track,
    _set_recursive_ownership,
    _validate_group,
)

CollisionPolicy = Literal["replace"]
LegacyStarted = Callable[[int], None]
LegacyProgress = Callable[[str, int, int, str, str, str], None]


@dataclass(frozen=True)
class CopySetRequest:
    """Resolved library selection and publication policy for one portable copy."""

    library: Path
    output: Path
    tracks: tuple[str | Path, ...] = ()
    playlist: Path | None = None
    owner: str = "share:share"
    collision_policy: CollisionPolicy = "replace"


class CopySetUseCase:
    """Validate, copy, and publish a portable set without opening a catalog."""

    def __init__(
        self,
        *,
        owner_resolver: OwnerResolver | None = None,
        ownership_setter: OwnershipSetter | None = None,
    ) -> None:
        self._owner_resolver = owner_resolver or _resolve_owner
        self._ownership_setter = ownership_setter or _set_recursive_ownership

    def execute(
        self, request: CopySetRequest, *, progress: ProgressSink | None = None
    ) -> SetCopyResult:
        library = self._resolve_library(request.library)
        output = request.output.resolve()
        if request.collision_policy != "replace":
            raise ValueError(f"unsupported collision policy: {request.collision_policy}")
        if output == library or output.is_relative_to(library):
            raise ValueError("--output must be outside --library to keep the library read-only")
        if request.playlist is None and not request.tracks:
            raise ValueError("At least one --playlist or --track is required")

        playlist_path = self._resolve_playlist(request.playlist)
        entries = self._plan_entries(library, playlist_path, request.tracks)
        if not entries:
            raise ValueError("No tracks found")

        uid, gid = self._owner_resolver(request.owner)
        output.mkdir(parents=True, exist_ok=True)
        output = output.resolve()
        playlist_name = playlist_path.name if playlist_path is not None else "playlist.m3u8"
        playlist_out = output / playlist_name
        text_out = output / f"{Path(playlist_name).stem}.txt"
        width = max(2, len(str(len(entries))))
        playlist_lines = ["#EXTM3U"]
        text_lines = ["ORDER\tGROUP\tFILE\tSOURCE"]
        last_group: str | None = None
        if progress is not None:
            progress(ProgressEvent("copy_started", 0, len(entries), str(output)))

        for index, (source, source_label, group) in enumerate(entries, 1):
            number = f"{index:0{width}d}"
            target_name = f"{number} - {source.name}"
            components = group.split("/") if group else []
            target_rel = "/".join((*components, target_name))
            if progress is not None:
                progress(ProgressEvent("copy_item_started", index - 1, len(entries), target_rel))
            with _open_target_directory(output, components, group) as (safe_dir, directory_fd):
                _copy_track_atomic(source, safe_dir, target_name, directory_fd)
            if progress is not None:
                progress(ProgressEvent("copy_item_finished", index, len(entries), target_rel))
            if group != last_group:
                if group:
                    playlist_lines.append(f"#EXTGRP:{group}")
                last_group = group
            playlist_lines.append(target_rel)
            text_lines.append(f"{number}\t{group}\t{target_name}\t{source_label}")

        _publish_text(playlist_out, "\n".join(playlist_lines) + "\n")
        _publish_text(text_out, "\n".join(text_lines) + "\n")
        self._ownership_setter(output, uid, gid)
        if progress is not None:
            progress(ProgressEvent("copy_finished", len(entries), len(entries), str(output)))
        return SetCopyResult(len(entries), playlist_out, text_out)

    @staticmethod
    def _resolve_library(library: Path) -> Path:
        if not library.is_dir():
            raise ValueError(f"Library does not exist or is not a directory: {library}")
        return library.resolve()

    @staticmethod
    def _resolve_playlist(playlist: Path | None) -> Path | None:
        if playlist is None:
            return None
        if not playlist.is_file():
            raise ValueError(f"Playlist not found: {playlist}")
        resolved = playlist.resolve()
        if resolved.suffix.lower() not in {".m3u", ".m3u8"}:
            raise ValueError(f"Playlist must have a .m3u or .m3u8 extension: {playlist}")
        return resolved

    @staticmethod
    def _plan_entries(
        library: Path,
        playlist: Path | None,
        tracks: Sequence[str | Path],
    ) -> list[tuple[Path, str, str]]:
        entries: list[tuple[Path, str, str]] = []
        current_group = ""
        if playlist is not None:
            for raw_line in playlist.read_text(encoding="utf-8").splitlines():
                line = raw_line.removesuffix("\r").removeprefix("\ufeff").strip()
                if not line:
                    continue
                if line.startswith("#EXTGRP:"):
                    current_group = _validate_group(line.removeprefix("#EXTGRP:"))
                    continue
                if line.startswith("#"):
                    continue
                entries.append(_resolve_track(library, line, current_group))
        entries.extend(_resolve_track(library, str(track), current_group) for track in tracks)
        return entries


def copy_set(
    *,
    library: Path,
    output: Path,
    tracks: Sequence[str | Path] = (),
    playlist: Path | None = None,
    owner: str = "share:share",
    started: LegacyStarted | None = None,
    progress: LegacyProgress | None = None,
    owner_resolver: OwnerResolver | None = None,
    ownership_setter: OwnershipSetter | None = None,
) -> SetCopyResult:
    """Compatibility call shape for callers of the pre-boundary copy function."""

    def adapt(event: ProgressEvent) -> None:
        if event.kind == "copy_started" and started is not None:
            started(event.total or 0)
        if progress is None or event.subject is None:
            return
        if event.kind == "copy_item_started":
            progress("before", (event.completed or 0) + 1, event.total or 0, "", "", event.subject)
        elif event.kind == "copy_item_finished":
            progress("after", event.completed or 0, event.total or 0, "", "", event.subject)

    return CopySetUseCase(
        owner_resolver=owner_resolver,
        ownership_setter=ownership_setter,
    ).execute(
        CopySetRequest(
            library=library,
            output=output,
            tracks=tuple(tracks),
            playlist=playlist,
            owner=owner,
        ),
        progress=adapt if started is not None or progress is not None else None,
    )


__all__ = ["CopySetRequest", "CopySetUseCase", "SetCopyResult", "copy_set"]
