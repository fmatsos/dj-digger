"""Safely copy an ordered DJ set from a read-only music library."""

from __future__ import annotations

import os
import secrets
import shutil
import stat
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SetCopyResult:
    """Files published by one set copy."""

    total: int
    playlist: Path
    text_list: Path


CopyStarted = Callable[[int], None]
CopyProgress = Callable[[str, int, int, str, str, str], None]
OwnerResolver = Callable[[str], tuple[int, int]]
OwnershipSetter = Callable[[Path, int, int], None]


def copy_set(
    *,
    library: Path,
    output: Path,
    tracks: Sequence[str | Path] = (),
    playlist: Path | None = None,
    owner: str = "share:share",
    started: CopyStarted | None = None,
    progress: CopyProgress | None = None,
    owner_resolver: OwnerResolver | None = None,
    ownership_setter: OwnershipSetter | None = None,
) -> SetCopyResult:
    """Copy playlist entries then explicit tracks and atomically publish manifests."""
    if not library.is_dir():
        raise ValueError(f"Library does not exist or is not a directory: {library}")
    library = library.resolve()
    output = output.resolve()
    if output == library or output.is_relative_to(library):
        raise ValueError("--output must be outside --library to keep the library read-only")
    if playlist is None and not tracks:
        raise ValueError("At least one --playlist or --track is required")

    playlist_path: Path | None = None
    if playlist is not None:
        if not playlist.is_file():
            raise ValueError(f"Playlist not found: {playlist}")
        playlist_path = playlist.resolve()
        if playlist_path.suffix.lower() not in {".m3u", ".m3u8"}:
            raise ValueError(f"Playlist must have a .m3u or .m3u8 extension: {playlist}")

    entries: list[tuple[Path, str, str]] = []
    current_group = ""
    if playlist_path is not None:
        for raw_line in playlist_path.read_text(encoding="utf-8").splitlines():
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
    if not entries:
        raise ValueError("No tracks found")

    uid, gid = (owner_resolver or _resolve_owner)(owner)
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    playlist_name = playlist_path.name if playlist_path is not None else "playlist.m3u8"
    playlist_out = output / playlist_name
    text_out = output / f"{Path(playlist_name).stem}.txt"
    width = max(2, len(str(len(entries))))
    playlist_lines = ["#EXTM3U"]
    text_lines = ["ORDER\tGROUP\tFILE\tSOURCE"]
    last_group: str | None = None
    if started is not None:
        started(len(entries))

    for index, (source, source_label, group) in enumerate(entries, 1):
        number = f"{index:0{width}d}"
        target_name = f"{number} - {source.name}"
        components = group.split("/") if group else []
        target_rel = "/".join((*components, target_name))
        if progress is not None:
            progress("before", index, len(entries), group, source_label, target_rel)
        with _open_target_directory(output, components, group) as (safe_dir, directory_fd):
            _copy_track_atomic(source, safe_dir, target_name, directory_fd)
        if progress is not None:
            progress("after", index, len(entries), group, source_label, target_rel)
        if group != last_group:
            if group:
                playlist_lines.append(f"#EXTGRP:{group}")
            last_group = group
        playlist_lines.append(target_rel)
        text_lines.append(f"{number}\t{group}\t{target_name}\t{source_label}")

    _publish_text(playlist_out, "\n".join(playlist_lines) + "\n")
    _publish_text(text_out, "\n".join(text_lines) + "\n")
    (ownership_setter or _set_recursive_ownership)(output, uid, gid)
    return SetCopyResult(len(entries), playlist_out, text_out)


def _validate_group(raw_group: str) -> str:
    group = raw_group.strip()
    if not group:
        raise ValueError("Empty #EXTGRP is not allowed")
    if group.startswith("/"):
        raise ValueError(f"Absolute #EXTGRP paths are not allowed: {group}")
    if "\n" in group or "\r" in group:
        raise ValueError("Invalid #EXTGRP value")
    components = group.split("/")
    if any(not component or component in {".", ".."} for component in components):
        raise ValueError(f"Unsafe #EXTGRP path: {group}")
    return group


def _resolve_track(library: Path, raw_value: str, group: str) -> tuple[Path, str, str]:
    raw = raw_value.removesuffix("\r").strip()
    if raw.startswith("file://"):
        raw = raw.removeprefix("file://")
    elif "://" in raw and _looks_like_uri(raw):
        raise ValueError(f"Remote playlist entries are not supported: {raw}")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = library / candidate
    try:
        canonical = candidate.resolve(strict=True)
    except FileNotFoundError:
        raise ValueError(f"Track not found: {raw}") from None
    if not canonical.is_file():
        raise ValueError(f"Track is not a regular file: {raw}")
    if not canonical.is_relative_to(library):
        raise ValueError(f"Track is outside the library: {raw}")
    return canonical, canonical.relative_to(library).as_posix(), group


def _looks_like_uri(value: str) -> bool:
    scheme, separator, _rest = value.partition("://")
    return bool(separator and scheme and scheme[0].isalpha()) and all(
        character.isalnum() or character in "+.-" for character in scheme
    )


def _publish_text(destination: Path, contents: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, prefix=".playlist.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _open_target_directory(
    output: Path, components: Sequence[str], group: str
) -> Iterator[tuple[Path, int | None]]:
    target_dir = output.joinpath(*components)
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        # Portable fallback: resolve immediately before and after mkdir. Atomic file
        # replacement still applies, but platforms without dir_fd cannot close the race.
        if not target_dir.resolve().is_relative_to(output):
            raise ValueError(f"Unsafe #EXTGRP path: {group}")
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target_dir.resolve().is_relative_to(output):
            raise ValueError(f"Unsafe #EXTGRP path: {group}")
        yield target_dir, None
        return

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd = os.open(output, flags)
    try:
        for component in components:
            try:
                os.mkdir(component, dir_fd=current_fd)
            except FileExistsError:
                pass
            try:
                child_fd = os.open(component, flags, dir_fd=current_fd)
            except OSError:
                raise ValueError(f"Unsafe #EXTGRP path: {group}") from None
            os.close(current_fd)
            current_fd = child_fd
        yield target_dir, current_fd
    finally:
        os.close(current_fd)


def copy_track_atomic(
    source: Path,
    target_dir: Path,
    target_name: str,
    directory_fd: int | None,
    *,
    expected_size: int | None = None,
    expected_mtime_ns: int | None = None,
) -> None:
    if directory_fd is None:
        _copy_track_atomic_portable(
            source,
            target_dir,
            target_name,
            expected_size=expected_size,
            expected_mtime_ns=expected_mtime_ns,
        )
        return
    try:
        destination_status = os.stat(target_name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        destination_status = None
    if destination_status is not None and not stat.S_ISREG(destination_status.st_mode):
        kind = "symbolic link" if stat.S_ISLNK(destination_status.st_mode) else "not a regular file"
        raise ValueError(f"Refusing to overwrite destination {kind}: {target_dir / target_name}")

    temporary_name = f".track.{secrets.token_hex(12)}"
    temporary_fd = os.open(
        temporary_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        source_fd = _open_source(source)
        with (
            os.fdopen(source_fd, "rb") as source_stream,
            os.fdopen(temporary_fd, "wb") as target_stream,
        ):
            temporary_fd = -1
            source_status = os.fstat(source_stream.fileno())
            _verify_source_identity(source, source_status, expected_size, expected_mtime_ns)
            shutil.copyfileobj(source_stream, target_stream)
            target_stream.flush()
            _verify_source_unchanged(source, source_stream.fileno(), source_status)
            os.fchmod(target_stream.fileno(), stat.S_IMODE(source_status.st_mode))
            os.utime(
                target_stream.fileno(),
                ns=(source_status.st_atime_ns, source_status.st_mtime_ns),
            )
        os.replace(
            temporary_name,
            target_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _copy_track_atomic(
    source: Path, target_dir: Path, target_name: str, directory_fd: int | None
) -> None:
    """Compatibility boundary for callers that instrument the set-copy operation."""
    copy_track_atomic(source, target_dir, target_name, directory_fd)


def _copy_track_atomic_portable(
    source: Path,
    target_dir: Path,
    target_name: str,
    *,
    expected_size: int | None,
    expected_mtime_ns: int | None,
) -> None:
    destination = target_dir / target_name
    if destination.is_symlink():
        raise ValueError(f"Refusing to overwrite destination symbolic link: {destination}")
    if destination.exists() and not destination.is_file():
        raise ValueError(f"Refusing to overwrite destination not a regular file: {destination}")
    descriptor, temporary_value = tempfile.mkstemp(prefix=".track.", dir=target_dir)
    os.close(descriptor)
    temporary = Path(temporary_value)
    try:
        source_fd = _open_source(source)
        with os.fdopen(source_fd, "rb") as source_stream, temporary.open("wb") as target_stream:
            source_status = os.fstat(source_stream.fileno())
            _verify_source_identity(source, source_status, expected_size, expected_mtime_ns)
            shutil.copyfileobj(source_stream, target_stream)
            target_stream.flush()
            _verify_source_unchanged(source, source_stream.fileno(), source_status)
            os.fchmod(target_stream.fileno(), stat.S_IMODE(source_status.st_mode))
            os.utime(
                target_stream.fileno(),
                ns=(source_status.st_atime_ns, source_status.st_mtime_ns),
            )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _open_source(source: Path) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(source, flags)
    except OSError:
        raise ValueError(f"Refusing unsafe or missing source track: {source}") from None


def _verify_source_identity(
    source: Path,
    status: os.stat_result,
    expected_size: int | None,
    expected_mtime_ns: int | None,
) -> None:
    if not stat.S_ISREG(status.st_mode):
        raise ValueError(f"Refusing source track that is not a regular file: {source}")
    if (expected_size is not None and status.st_size != expected_size) or (
        expected_mtime_ns is not None and status.st_mtime_ns != expected_mtime_ns
    ):
        raise ValueError(f"track identity changed; rescan: {source}")


def _verify_source_unchanged(source: Path, source_fd: int, before: os.stat_result) -> None:
    after = os.fstat(source_fd)
    try:
        path_status = source.stat(follow_symlinks=False)
    except FileNotFoundError:
        raise ValueError(f"track identity changed during copy; rescan: {source}") from None
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields) or (
        path_status.st_dev != after.st_dev or path_status.st_ino != after.st_ino
    ):
        raise ValueError(f"track identity changed during copy; rescan: {source}")


def _set_recursive_ownership(output: Path, uid: int, gid: int) -> None:
    if os.name != "posix":
        raise ValueError("recursive ownership is not supported on this platform")
    for _root, directories, files, directory_fd in os.fwalk(
        output, topdown=False, follow_symlinks=False
    ):
        for name in (*directories, *files):
            os.chown(name, uid, gid, dir_fd=directory_fd, follow_symlinks=False)
    os.chown(output, uid, gid, follow_symlinks=False)


def _resolve_owner(owner: str) -> tuple[int, int]:
    user, group = _validate_owner(owner)
    if os.name != "posix":
        raise ValueError("recursive ownership is not supported on this platform")
    if user.isdecimal() and group.isdecimal():
        return int(user), int(group)
    import grp
    import pwd

    try:
        uid = int(user) if user.isdecimal() else pwd.getpwnam(user).pw_uid
    except KeyError:
        raise ValueError(f"unknown user: {user}") from None
    try:
        gid = int(group) if group.isdecimal() else grp.getgrnam(group).gr_gid
    except KeyError:
        raise ValueError(f"unknown group: {group}") from None
    return uid, gid


def _validate_owner(owner: str) -> tuple[str, str]:
    user, separator, group = owner.partition(":")
    if owner.count(":") != 1 or not separator or not user or not group:
        raise ValueError("--owner must use the USER:GROUP format")
    return user, group
